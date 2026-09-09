# Mattermost & Ollama Bridge Helm Chart

A Production-Grade Raspberry Pi K8S Cluster umbrella Helm chart that deploys a self-hosted **Mattermost Team Edition** collaboration platform backed by **PostgreSQL**, integrated seamlessly with a custom **Ollama AI Bridge** subchart for local LLM chatbot interactions.

---

## ⚡ TL;DR
📝 **The Chicken-and-Egg Problem:** If you are setting up a brand new Mattermost server, you have to boot it up first to generate tokens, then redeploy the bridge. If you already have a server, you can do it all in one pass.

### ⚙️ Universal Prerequisites (All Setups)
1. Configure Podman for insecure registry pushes if you haven't already.
2. Create a `local-values.yaml` file in the root directory (copy from `local-values.yaml.template`).

#### Setup A. If this is a BRAND NEW Mattermost server (skip to B. if you already have a server)
1. Put placeholder values in your 'local-values.yaml' for the chatbot tokens so the deployment can boot up.  
2. Install the stack with Helm (from the root folder):  
   ```bash
   helm upgrade --install mattermost-stack . -f local-values.yaml
   ```
3. Continue to Setup B.  

#### Setup B: You have a running Mattermost server  
1. **Create your Mattermost chatbots and capture the tokens:**  
   ```bash
   mmctl bot create <bot-username> --display-name "<Friendly Display Name>" --description "<Description bot of the>" --with-token
   ```
2. Update `local-values.yaml` file with chatbot tokens.   
3. Build and push the Ollama bridge container:  
   ```bash
   cd charts/ollama-bridge/
   sudo ./builbot.sh
   ```
4. Install the stack with Helm (from the root folder):  
   ```bash
   helm upgrade --install mattermost-stack . -f local-values.yaml
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
* An accessable Ollama server  

---

### Step 1: Configure Your Local Registry & Podman
To ensure your cluster nodes can pull container builds correctly without hardcoding machine names:

1. **Map a friendly local registry alias** on your nodes (add to `/etc/hosts`):  
   ```text
   <YOUR_REGISTRY_NODE_IP> local-registry
   ```

2. **Configure Podman for insecure registry pushes**  
   create `/etc/containers/registries.conf.d/local-registry.conf`:  
   ```yaml
   [[registry]]
   location = "local-registry:5000"
   insecure = true
   ```

---

### Step 2: Build (or rebuild) and Push the Ollama Bridge Image
The `ollama-bridge` subchart runs a custom Python application. Build and push it directly to your local registry:

1. **Navigate into the subchart directory:**
   ```bash
   cd charts/ollama-bridge/
   ```

2. **Build and push the image:**  
   📝 You can use the included script or do it manually. The script is useful for rebuilding after modifiying `main.py`  

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
   📝 Use the `local-values.yaml.template` to align with `main.py`; just populate it and rename it `local-values.yaml` 

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

| Parameter | local-value | Description | Default |
|---|---|---|---|
| `replicaCount` | replicaCount | Number of Mattermost replicas | `1` |
| `ollama-bridge.image.registry` | repository | Container registry host and port | `local-registry:5000` |
| `ollama-bridge.image.repository` | repository | Bridge container repository path | `library/ollama-bridge` |
| `ollama-bridge.image.tag` | tag | Bridge container tag version | `latest` |
| `ollama-bridge.env.OLLAMA_HOST` | OLLAMA_HOST | Target Ollama backend API endpoint | `http://ollama.svc.cluster.local:11434` |
| `ollama-bridge.env.OLLAMA_TIMEOUT`| OLLAMA_TIMEOUT | Timeout to Ollama backend  | `60` |
| `ollama-bridge.env.OLLAMA_MODELS` | models | Comma-separated list of Ollama models | `<first model in list>` |
| `ollama-bridge.env.MATTERMOST_BOT_TOKENS` | botTokens | Comma-separated list of Bot tokens | `""` |

---

## 🔒 Security Best Practices
* **Take care to not commit `local-values.yaml`** to source control: It should be configured to be explicitly blocked via `.gitignore`.
* Kubernetes `Secrets` handle sensitive connection strings and bot tokens safely at runtime without exposing them in plaintext deployment specs.

--- 

## 🚀 Performance Best Practices  
* Preload the Ollama models into memory.  
```bash
curl http://<local ip address>:11434/api/generate -d '{"model": "huihui_ai/qwen3-abliterated:14b", "prompt": "hi", "stream": false}'
```  
* Set a forgiving timeout; depending on your Ollama server's RAM bandwidth (i.e.; 120)  

⚙️  🌟 
