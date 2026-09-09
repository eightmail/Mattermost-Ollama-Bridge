# Mattermost & Ollama Bridge Helm Chart

A Production-Grade Raspberry Pi K8S Cluster umbrella Helm chart that deploys a self-hosted **Mattermost Team Edition** collaboration platform backed by **PostgreSQL**, integrated seamlessly with a custom **Ollama AI Bridge** subchart for local LLM chatbot interactions.

---

## ⚡ TL;DR
*📝 if you don't already have a Mattermost server, you will have to rebuild the ollama-bridge with the bot tokens you create in the Mattermost server after you bring it up. 

1. Create Mattermost bots and get tokens 
   ```bash
   mmctl bot create <bot-username> --display-name "<Friendly Display Name>" --description "<Description of the bot>" --with-token
   ```
2. Configure Podman for insecure registry pushes 
3. Create a `local-values.yaml` file in the root directory to define your bot tokens, model mappings, and deployment overrides. 
   *NOTE: Use the `local-values.yaml.template` file as a template to align with `main.py`* 
4. Install the stack with helm 
   ```bash
   helm upgrade --install mattermost-stack . -f local-values.yaml
   ```
4. Build and push the image using the script:
   ```bash
    charts/ollama-bridge/builbot.sh
   ```

---

## 🌟 Key Architecture & Features

* **Umbrella Chart Pattern:** Modular design housing the core Mattermost stack and decoupling the `ollama-bridge` as a dedicated subchart.
* **1-to-1 Multi-Bot AI Routing:** Run multiple AI chatbots concurrently in separate Mattermost channels, each mapped 1-to-1 to its own specific Ollama model (e.g., Llama 3, Qwen, Abliterated models).
* **Node-Agnostic Local Registry:** Uses a clean, portable local registry pattern (`local-registry:5000`) rather than hardcoding specific machine names into configurations.
* **Greenfield & Brownfield Flexibility:** Designed for instant out-of-the-box greenfield deployments while featuring persistence options for adopting existing production Persistent Volume Claims (PVCs).
* **Secure Credential Management:** Utilizes native Kubernetes `Secret` objects with automatic password generation for fresh installs while supporting manual overrides.

---

## 📁 Getting Started & Setup

### Prerequisites
* A Kubernetes cluster (Tested on K3s)
* Helm 3.x installed
* An active Ingress Controller (e.g., Traefik) and dynamic storage provisioner (e.g., `local-path`)
* An insecure local container registry running on your network (e.g., at port `5000`).

---

### Step 1: Configure Your Local Registry & Podman
To ensure your cluster nodes can pull container builds correctly without hardcoding machine names:

1. **Map a friendly local registry alias** on your nodes (add to `/etc/hosts`):
   <YOUR_REGISTRY_NODE_IP> local-registry

2. **Configure Podman for insecure registry pushes** (create `/etc/containers/registries.conf.d/local-registry.conf`):
   [[registry]]
   location = "local-registry:5000"
   insecure = true

---

### Step 2: Build (or rebuild) and Push the Ollama Bridge Image
The `ollama-bridge` subchart runs a custom Python application. Build and push it directly to your local registry:

1. **Navigate into the subchart directory:**
   ```bash
   cd charts/ollama-bridge/
   ```

2. **Build and push the image:**
   *📝 You can use the included script or do it manually. The script is useful for rebuilding after modifiying `main.py`
   a. Using the included script
      ```bash
      sudo ./buildbot.sh
      ```
   b. Building it manually
      ```bash 
      sudo podman build -t local-registry:5000/library/ollama-bridge:latest .
      sudo podman push local-registry:5000/library/ollama-bridge:latest
      ```

3. **Return to the umbrella chart root directory:**
   ```bash
   cd ../../
   ```

---

### Step 3: Configure Deployment (`local-values.yaml`)

1. Create a `local-values.yaml` file in the root directory to define your bot tokens, model mappings, and deployment overrides. 
   *📝 Use the `local-values.yaml.template` to align with `main.py`; just populate it and rename it `local-values.yaml` 

---

### Step 4: Deploy the Stack

1. **Lint your chart to verify configuration syntax:**
   ```bash
   helm lint . -f local-values.yaml
   ```

2. **Deploy or upgrade your release:**
   ```bash
   helm upgrade --install mattermost-stack . -f local-values.yaml
   ```

3. **Verify running pods:**
   ```bash
   kubectl get pods
   kubectl logs deployment/mattermost-stack-ollama-bridge -f
   ```
 
   You should see confirmation logs showing each bot user ID successfully registered and mapped 1-to-1 with its assigned Ollama model!

---

## 📌 Configuration Parameters Reference

| Parameter | Description | Default |
|---|---|---|
| `replicaCount` | Number of Mattermost replicas | `1` |
| `ollama-bridge.image.registry` | Container registry host and port | `local-registry:5000` |
| `ollama-bridge.image.repository` | Bridge container repository path | `library/ollama-bridge` |
| `ollama-bridge.image.tag` | Bridge container tag version | `latest` |
| `ollama-bridge.env.OLLAMA_HOST` | Target Ollama backend API endpoint | `http://ollama.svc.cluster.local:11434` |
| `ollama-bridge.env.OLLAMA_MODELS` | Comma-separated list of Ollama models | `llama3:8b` |
| `ollama-bridge.env.MATTERMOST_BOT_TOKENS` | Comma-separated list of Bot tokens | `""` |

---

## 🔒 Security Best Practices
* **Take care to not commit `local-values.yaml`** to source control: It should be configured to be explicitly blocked via `.gitignore`.
* Kubernetes `Secrets` handle sensitive connection strings and bot tokens safely at runtime without exposing them in plaintext deployment specs.

--- 

⚙️  🌟 🚀 
