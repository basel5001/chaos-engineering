#!/usr/bin/env bash
set -euo pipefail

# Tear down a vCluster chaos environment

VCLUSTER_NAME="${1:-chaos-lab}"
NAMESPACE="${2:-chaos-engineering}"

echo "==> Deleting vCluster '${VCLUSTER_NAME}' from namespace '${NAMESPACE}'..."
vcluster delete "${VCLUSTER_NAME}" --namespace "${NAMESPACE}"

echo "==> Cleaning up kubeconfig..."
rm -f "./kubeconfig-${VCLUSTER_NAME}.yaml"

echo "==> Teardown complete."
