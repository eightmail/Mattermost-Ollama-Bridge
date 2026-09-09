#!/bin/bash
set -e

# ==============================================================================
# CONFIGURATION
# ==============================================================================
IMAGE_NAME="ollama-bridge"
IMAGE_TAG="latest"
# Use the exact namespace reference K3s expects
CANONICAL_IMAGE="docker.io/library/${IMAGE_NAME}:${IMAGE_TAG}"
LOCAL_IMAGE="localhost/${IMAGE_NAME}:${IMAGE_TAG}"
TARBALL_PATH="/tmp/${IMAGE_NAME}-image.tar"

echo $CANONICAL_IMAGE
echo $LOCAL_IMAGE
echo $TARBALL_PATH

# Ensure we are operating inside the subchart directory where the Dockerfile lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "--------------------------------------------------"
echo "Removing all local ollam-bridge images: ${CANONICAL_IMAGE}"
echo "--------------------------------------------------"
# Remove all variants of ollama-bridge images from the K3s containerd namespace
ctr -n k8s.io images rm \
  docker.io/library/ollama-bridge:latest \
  mattermost-ollama-bridge:latest \
  local/mattermost-ollama-bridge:latest 2>/dev/null || true

echo "All ollama-bridge images cleared from containerd!"

echo "--------------------------------------------------"
echo "Building and registering local image: ${CANONICAL_IMAGE}"
echo "--------------------------------------------------"

# 1. Clean up old images from K3s containerd namespace (k8s.io)
echo "-> Removing old image from K3s containerd (k8s.io)..."
sudo ctr -n k8s.io images rm "${CANONICAL_IMAGE}" || true
sudo ctr -n k8s.io images rm "${LOCAL_IMAGE}" || true

# 2. Purge the old image from Podman/Docker
echo "-> Purging old image from local build engine..."
podman rmi -f "${CANONICAL_IMAGE}" || true
podman rmi -f "${LOCAL_IMAGE}" || true

# 3. Remove temporary tarballs left from previous runs
echo "-> Clearing temporary build artifacts..."
rm -f "${TARBALL_PATH}"

# 4. Build the image fresh from scratch with no cache
echo "-> Building fresh container image (--no-cache)..."
podman build --no-cache -t "${LOCAL_IMAGE}" .

# 5. Tag locally for canonical docker.io format
podman tag "${LOCAL_IMAGE}" "${CANONICAL_IMAGE}"

# 6. Save the image to a temporary tarball
echo "-> Exporting image to tarball..."
podman save "${CANONICAL_IMAGE}" -o "${TARBALL_PATH}"

# 7. Import the clean image directly into K3s containerd k8s.io namespace
echo "-> Importing clean image into K3s containerd (k8s.io)..."
ctr -n k8s.io images import "${TARBALL_PATH}"
echo "push it to the local docker registry"
podman tag docker.io/library/ollama-bridge:latest rapik8szero:5000/library/ollama-bridge:latest
podman push --tls-verify=false rapik8szero:5000/library/ollama-bridge:latest
podman push rapik8szero:5000/library/ollama-bridge:v2

# 8. Cleanup the tarball
echo "-> Clearing temporary build artifacts..."
rm -f "${TARBALL_PATH}"

# ==============================================================================
# PRINT INFO
# ==============================================================================
echo "--------------------------------------------------"
echo "Success! Image '${CANONICAL_IMAGE}' is ready."
echo "You can now deploy or upgrade your stack using Helm: copy and paste these commands if needed:"
echo ""
echo "helm upgrade mattermost-stack ../../ -f ../../local-values.yaml"
echo "kubectl rollout restart deployment -l app.kubernetes.io/name=ollama-bridge"
echo "kubectl logs deployment/mattermost-stack-ollama-bridge  -f"
echo "--------------------------------------------------"

exit 0
