import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from requests.exceptions import RequestException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ollama-exporter")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", 15))
EXPORTER_PORT = int(os.environ.get("EXPORTER_PORT", 9099))
PROXY_PORT = int(os.environ.get("PROXY_PORT", 11435))
PROXY_ENABLED = os.environ.get("PROXY_ENABLED", "true").lower() in ("1", "true", "yes")

INSTRUMENTED_PATHS = {"/api/generate", "/api/chat"}
HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
    }
)

# Poll-based metrics (VRAM, models, context limits)
OLLAMA_UP = Gauge("ollama_up", "1 if Ollama is healthy, 0 if down")
MODELS_TOTAL = Gauge("ollama_models_total", "Total number of models available")
MODELS_LOADED = Gauge("ollama_models_loaded", "Number of currently loaded models")
MODEL_SIZE = Gauge("ollama_model_size_bytes", "Model file size by model name", ["model"])
MODEL_VRAM = Gauge("ollama_model_vram_bytes", "VRAM used per model", ["model"])
MODEL_RAM = Gauge("ollama_model_ram_bytes", "RAM used per model", ["model"])
MODEL_CONTEXT_LENGTH = Gauge(
    "ollama_model_context_length",
    "Maximum context window in tokens (from /api/show)",
    ["model"],
)
SCRAPE_DURATION = Gauge("ollama_scrape_duration_seconds", "How long polling scrape takes")
SCRAPE_ERRORS = Counter("ollama_scrape_errors_total", "Polling scrape errors")

# Proxy-captured metrics (per request via /api/generate and /api/chat)
REQUESTS_TOTAL = Counter(
    "ollama_requests_total",
    "Completed generate/chat requests",
    ["model", "endpoint"],
)
PROMPT_TOKENS_TOTAL = Counter(
    "ollama_prompt_tokens_total",
    "Prompt tokens processed",
    ["model", "endpoint"],
)
COMPLETION_TOKENS_TOTAL = Counter(
    "ollama_completion_tokens_total",
    "Completion tokens generated",
    ["model", "endpoint"],
)
LAST_PROMPT_TOKENS = Gauge(
    "ollama_last_prompt_tokens",
    "Prompt tokens in the last completed request",
    ["model"],
)
LAST_COMPLETION_TOKENS = Gauge(
    "ollama_last_completion_tokens",
    "Completion tokens in the last completed request",
    ["model"],
)
CONTEXT_USED_RATIO = Gauge(
    "ollama_context_used_ratio",
    "Last request (prompt+completion) tokens / model context length",
    ["model"],
)
TOKENS_PER_SECOND = Gauge(
    "ollama_tokens_per_second",
    "Completion tokens per second on the last request",
    ["model"],
)
REQUEST_DURATION = Histogram(
    "ollama_request_duration_seconds",
    "End-to-end request duration",
    ["model", "endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
PROMPT_EVAL_DURATION = Histogram(
    "ollama_prompt_eval_duration_seconds",
    "Prompt evaluation duration",
    ["model", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
EVAL_DURATION = Histogram(
    "ollama_eval_duration_seconds",
    "Token generation duration",
    ["model", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

# Populated by polling /api/show; used when recording proxy traffic.
_context_lengths: dict[str, int] = {}


def context_length_from_show(payload: dict) -> int:
    info = payload.get("model_info") or {}
    for key, value in info.items():
        if key.endswith("context_length"):
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def record_usage(payload: dict, endpoint: str) -> None:
    if not payload.get("done"):
        return

    model = payload.get("model") or "unknown"
    prompt_tokens = int(payload.get("prompt_eval_count") or 0)
    completion_tokens = int(payload.get("eval_count") or 0)
    total_ns = int(payload.get("total_duration") or 0)
    prompt_ns = int(payload.get("prompt_eval_duration") or 0)
    eval_ns = int(payload.get("eval_duration") or 0)

    REQUESTS_TOTAL.labels(model=model, endpoint=endpoint).inc()
    if prompt_tokens:
        PROMPT_TOKENS_TOTAL.labels(model=model, endpoint=endpoint).inc(prompt_tokens)
    if completion_tokens:
        COMPLETION_TOKENS_TOTAL.labels(model=model, endpoint=endpoint).inc(completion_tokens)

    LAST_PROMPT_TOKENS.labels(model=model).set(prompt_tokens)
    LAST_COMPLETION_TOKENS.labels(model=model).set(completion_tokens)

    if eval_ns > 0 and completion_tokens > 0:
        TOKENS_PER_SECOND.labels(model=model).set(completion_tokens / (eval_ns / 1e9))

    ctx = _context_lengths.get(model, 0)
    if ctx > 0:
        used = prompt_tokens + completion_tokens
        CONTEXT_USED_RATIO.labels(model=model).set(used / ctx)

    if total_ns > 0:
        REQUEST_DURATION.labels(model=model, endpoint=endpoint).observe(total_ns / 1e9)
    if prompt_ns > 0:
        PROMPT_EVAL_DURATION.labels(model=model, endpoint=endpoint).observe(prompt_ns / 1e9)
    if eval_ns > 0:
        EVAL_DURATION.labels(model=model, endpoint=endpoint).observe(eval_ns / 1e9)

    logger.info(
        "request model=%s endpoint=%s prompt_tokens=%s completion_tokens=%s",
        model,
        endpoint,
        prompt_tokens,
        completion_tokens,
    )


def fetch_tags():
    response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
    response.raise_for_status()
    return response.json().get("models", [])


def fetch_ps():
    response = requests.get(f"{OLLAMA_HOST}/api/ps", timeout=5)
    response.raise_for_status()
    return response.json().get("models", [])


def fetch_show(model_name: str) -> dict:
    response = requests.post(
        f"{OLLAMA_HOST}/api/show",
        json={"name": model_name},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_health():
    response = requests.get(OLLAMA_HOST, timeout=5)
    response.raise_for_status()
    return response.status_code == 200


def update_metrics():
    start_time = time.time()

    try:
        is_healthy = fetch_health()
        OLLAMA_UP.set(1 if is_healthy else 0)

        if is_healthy:
            tags = fetch_tags()
            MODELS_TOTAL.set(len(tags))

            MODEL_SIZE.clear()
            MODEL_CONTEXT_LENGTH.clear()
            for model in tags:
                name = model["name"]
                MODEL_SIZE.labels(model=name).set(model.get("size", 0))
                try:
                    show = fetch_show(name)
                    ctx = context_length_from_show(show)
                    if ctx > 0:
                        _context_lengths[name] = ctx
                        MODEL_CONTEXT_LENGTH.labels(model=name).set(ctx)
                except RequestException as exc:
                    logger.warning("Could not fetch /api/show for %s: %s", name, exc)

            ps_models = fetch_ps()
            MODELS_LOADED.set(len(ps_models))

            MODEL_VRAM.clear()
            MODEL_RAM.clear()
            for model in ps_models:
                name = model["name"]
                size_total = model.get("size", 0)
                size_vram = model.get("size_vram", 0)
                MODEL_VRAM.labels(model=name).set(size_vram)
                MODEL_RAM.labels(model=name).set(max(0, size_total - size_vram))

        SCRAPE_DURATION.set(time.time() - start_time)

    except RequestException as exc:
        logger.error("Error fetching from Ollama: %s", exc)
        OLLAMA_UP.set(0)
        SCRAPE_ERRORS.inc()
    except Exception as exc:
        logger.error("Unexpected error: %s", exc)
        SCRAPE_ERRORS.inc()


def _request_wants_stream(body: bytes) -> bool:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return True
    return bool(payload.get("stream", True))


def _forward_headers(handler: BaseHTTPRequestHandler, upstream: requests.Response) -> None:
    for key, value in upstream.headers.items():
        if key.lower() not in HOP_BY_HOP_HEADERS:
            handler.send_header(key, value)
    handler.end_headers()


class OllamaProxyHandler(BaseHTTPRequestHandler):
    timeout = 600

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def do_PUT(self):
        self._proxy("PUT")

    def do_DELETE(self):
        self._proxy("DELETE")

    def _proxy(self, method: str):
        path = self.path.split("?", 1)[0]
        url = f"{OLLAMA_HOST}{self.path}"
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else None

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in ("host", "content-length")
        }

        instrument = (
            PROXY_ENABLED
            and method == "POST"
            and path in INSTRUMENTED_PATHS
            and body
        )

        try:
            if instrument and not _request_wants_stream(body):
                upstream = requests.request(
                    method,
                    url,
                    headers=headers,
                    data=body,
                    timeout=self.timeout,
                )
                self.send_response(upstream.status_code)
                _forward_headers(self, upstream)
                if upstream.content:
                    self.wfile.write(upstream.content)
                if upstream.ok:
                    try:
                        record_usage(upstream.json(), path)
                    except json.JSONDecodeError:
                        pass
                return

            upstream = requests.request(
                method,
                url,
                headers=headers,
                data=body,
                stream=True,
                timeout=self.timeout,
            )
            self.send_response(upstream.status_code)
            _forward_headers(self, upstream)

            if instrument:
                for line in upstream.iter_lines(decode_unicode=False):
                    if not line:
                        continue
                    self.wfile.write(line + b"\n")
                    self.wfile.flush()
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        record_usage(chunk, path)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
            else:
                for chunk in upstream.iter_content(chunk_size=8192):
                    if chunk:
                        self.wfile.write(chunk)
                        self.wfile.flush()

        except RequestException as exc:
            logger.error("Proxy error %s %s: %s", method, path, exc)
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            message = json.dumps({"error": str(exc)}).encode("utf-8")
            self.wfile.write(message)


def polling_loop():
    while True:
        update_metrics()
        time.sleep(SCRAPE_INTERVAL)


def run_proxy():
    server = HTTPServer(("0.0.0.0", PROXY_PORT), OllamaProxyHandler)
    logger.info("Ollama proxy listening on port %s (forwards to %s)", PROXY_PORT, OLLAMA_HOST)
    server.serve_forever()


if __name__ == "__main__":
    logger.info("Metrics on :%s | Ollama upstream: %s", EXPORTER_PORT, OLLAMA_HOST)
    logger.info("Poll interval: %ss | Proxy enabled: %s", SCRAPE_INTERVAL, PROXY_ENABLED)

    start_http_server(EXPORTER_PORT)
    threading.Thread(target=polling_loop, daemon=True).start()

    if PROXY_ENABLED:
        run_proxy()
    else:
        while True:
            time.sleep(3600)
