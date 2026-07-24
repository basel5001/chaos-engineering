# vCluster for Isolated Chaos Testing

## Why vCluster?

Running chaos experiments on production or shared clusters is risky. [vCluster](https://www.vcluster.com/) creates lightweight virtual Kubernetes clusters inside a host cluster, providing:

- **Isolation** — Chaos experiments cannot impact the host cluster or other tenants
- **Safety** — Pod kills, network faults, and DNS failures are contained
- **Repeatability** — Spin up identical environments for each experiment run
- **Speed** — vClusters start in seconds (vs minutes for full clusters)
- **Cost** — No additional cloud infrastructure needed

## Prerequisites

```bash
# Install vCluster CLI
curl -L -o vcluster "https://github.com/loft-sh/vcluster/releases/latest/download/vcluster-darwin-arm64"
chmod +x vcluster && sudo mv vcluster /usr/local/bin/

# Or via Homebrew
brew install loft-sh/tap/vcluster
```

## Usage

### Create a chaos environment

```bash
./setup.sh chaos-lab chaos-engineering
export KUBECONFIG=./kubeconfig-chaos-lab.yaml
```

### Deploy your target workloads

```bash
kubectl apply -f ../manifests/target-app/
```

### Run chaos experiments

```bash
chaos --manifest ../manifests/experiment-pod-kill.yml --kubeconfig ./kubeconfig-chaos-lab.yaml
```

### Tear down

```bash
./teardown.sh chaos-lab chaos-engineering
```

## Configuration

Edit `vcluster.yaml` to customize:

- Resource limits for the virtual control plane
- Node sync settings
- Networking configuration
- K3s distro settings

## CI Integration

Use vCluster in CI pipelines for automated chaos testing:

```yaml
- name: Create chaos environment
  run: ./vcluster/setup.sh ci-chaos-${{ github.run_id }}

- name: Run chaos experiments
  run: chaos --manifest manifests/experiment-pod-kill.yml
  env:
    KUBECONFIG: ./kubeconfig-ci-chaos-${{ github.run_id }}.yaml

- name: Teardown
  if: always()
  run: ./vcluster/teardown.sh ci-chaos-${{ github.run_id }}
```
