#!/usr/bin/env bash
set -euo pipefail

# Create a vCluster for isolated chaos experiments
# Prerequisites: vcluster CLI, kubectl with cluster access

VCLUSTER_NAME="${1:-chaos-lab}"
NAMESPACE="${2:-chaos-engineering}"

echo "==> Creating namespace ${NAMESPACE} (if not exists)..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "==> Creating vCluster '${VCLUSTER_NAME}' in namespace '${NAMESPACE}'..."
vcluster create "${VCLUSTER_NAME}" \
  --namespace "${NAMESPACE}" \
  --values "$(dirname "$0")/vcluster.yaml" \
  --connect=false

echo "==> Waiting for vCluster to be ready..."
vcluster wait "${VCLUSTER_NAME}" --namespace "${NAMESPACE}"

echo "==> Connecting to vCluster..."
vcluster connect "${VCLUSTER_NAME}" --namespace "${NAMESPACE}" --update-current=false \
  --kube-config ./kubeconfig-${VCLUSTER_NAME}.yaml

echo "==> vCluster ready! Use:"
echo "    export KUBECONFIG=./kubeconfig-${VCLUSTER_NAME}.yaml"
echo "    kubectl get nodes"
echo ""
echo "==> Run chaos experiments safely inside this isolated cluster."
