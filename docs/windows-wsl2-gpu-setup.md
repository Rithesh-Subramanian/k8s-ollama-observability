# Windows WSL2 & NVIDIA GPU Setup Guide

To run GPU-accelerated Kubernetes workloads (like Ollama and the DCGM exporter) locally on Windows, we leverage WSL2 (Windows Subsystem for Linux).

## Step 1: Windows Host Setup

1. **Install NVIDIA Drivers**: Ensure you have the latest NVIDIA Game Ready or Studio driver installed on your Windows 11 host. (Do *not* install a Linux display driver inside WSL2).
2. **Install WSL2**: Open an Administrator PowerShell prompt and run:
   ```powershell
   wsl --install -d Ubuntu
   ```
3. **Reboot** if prompted, and complete the Ubuntu setup (create username/password).

## Step 2: Verify GPU in WSL2

Open your `Ubuntu` terminal and run:
```bash
nvidia-smi
```
You should see your NVIDIA RTX 4060 listed. If it fails, ensure your Windows NVIDIA drivers are up to date and WSL2 is fully updated (`wsl --update`).

## Step 3: Install Docker & NVIDIA Container Toolkit in WSL2

While we will use k3s, we need Docker and the NVIDIA Container Toolkit installed in the WSL2 environment to provide the necessary Container Device Interface (CDI) configurations.

Run these commands inside your Ubuntu WSL2 terminal:

**1. Install Docker:**
```bash
# Add Docker's official GPG key:
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

# Install Docker
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to the docker group
sudo usermod -aG docker $USER
```
*(You may need to close and reopen your terminal for the group change to take effect).*

**2. Install NVIDIA Container Toolkit:**
```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
```

**3. Configure Docker to use NVIDIA runtime:**
```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

## Step 4: Test GPU in Container

Verify that containers can access the GPU:
```bash
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```
If you see the `nvidia-smi` output showing your 4060, your WSL2 environment is perfectly configured for GPU workloads!

## Next Steps

Now you can proceed with setting up the Kubernetes cluster using the project's Makefile:
```bash
make setup
```
