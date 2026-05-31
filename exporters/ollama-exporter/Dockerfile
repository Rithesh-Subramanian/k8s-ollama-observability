FROM python:3.12-slim

# Create non-root user
RUN groupadd -r exporter && useradd -r -g exporter -s /sbin/nologin exporter

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY exporter.py .

# Set permissions
RUN chown -R exporter:exporter /app

USER exporter

EXPOSE 9099 11435

CMD ["python", "-u", "exporter.py"]
