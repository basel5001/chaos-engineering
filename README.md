# Chaos Engineering Toolkit

![CI](https://github.com/basel5001/chaos-engineering/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Kubernetes](https://img.shields.io/badge/Kubernetes-326CE5?style=flat-square&logo=kubernetes&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![AWS Bedrock](https://img.shields.io/badge/AWS_Bedrock-FF9900?style=flat-square&logo=amazonaws&logoColor=white)

Kubernetes chaos engineering toolkit with AI-powered analysis via AWS Bedrock.

## Architecture

```
chaos-engineering/
├── src/
│   ├── experiments/       # Chaos experiment implementations
│   │   ├── pod_kill.py    # Random pod termination
│   │   ├── network_latency.py  # TC-based latency injection
│   │   ├── cpu_stress.py  # stress-ng CPU consumption
│   │   ├── disk_fill.py   # Disk space exhaustion
│   │   └── dns_failure.py # CoreDNS SERVFAIL injection
│   ├── runner/
│   │   ├── orchestrator.py  # Experiment plan execution
│   │   └── cli.py          # CLI entrypoint
│   ├── ai/
│   │   └── analyzer.py     # AWS Bedrock AI analysis
│   └── dashboard/
│       └── index.html       # Results visualization
├── manifests/             # Experiment plan YAML files (CRD-style)
├── terraform/             # IaC for K8s CronJob + IAM
├── tests/                 # Unit tests
└── .github/workflows/     # CI/CD pipelines
```

## Experiment Types

| Type | Description | Mechanism |
|------|-------------|-----------|
| `pod-kill` | Kill random pods | `kubectl delete pod` with grace=0 |
| `network-latency` | Inject network delay | Privileged pod running `tc qdisc netem` |
| `cpu-stress` | Consume CPU resources | `stress-ng` pod co-located on target node |
| `disk-fill` | Fill disk space | `dd` writing to hostPath volume |
| `dns-failure` | DNS resolution failures | CoreDNS configmap patching with SERVFAIL |

## Quick Start

```bash
# Install dependencies
make dev

# Run a dry-run experiment
make run

# Run with AI analysis
make run-analyze

# Run tests
make test

# Build Docker image
make build
```

## Usage

### CLI

```bash
# Dry-run an experiment plan
chaos --manifest manifests/experiment-pod-kill.yml --dry-run

# Live execution with AI analysis
chaos --manifest manifests/experiment-pod-kill.yml --analyze

# Output results as JSON
chaos --manifest manifests/experiment-network.yml --output json --outfile results.json
```

### Experiment Plan (YAML)

```yaml
apiVersion: chaos.xops.io/v1alpha1
kind: ChaosExperiment
metadata:
  name: kill-frontend-pods
spec:
  description: "Kill frontend pods to test self-healing"
  experiments:
    - name: kill-frontend
      type: pod-kill
      namespace: default
      label_selector: "app=frontend"
      kill_count: 2
      wait_seconds: 30
  steady_state:
    check: "kubectl get pods -l app=frontend --field-selector=status.phase=Running | wc -l"
    expected: "3"
```

## AI Features (AWS Bedrock)

The toolkit integrates with AWS Bedrock to provide:

1. **Results Analysis** — AI reviews experiment outcomes, identifies weaknesses, and suggests hardening measures
2. **Blast Radius Prediction** — Before running, predict which services/SLOs will be impacted
3. **Experiment Suggestions** — Describe your service and get AI-recommended chaos experiments

### Configuration

Set these environment variables (or use IRSA in EKS):

```bash
export AWS_DEFAULT_REGION=us-east-1
export BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
```

## Deployment

### Kubernetes CronJob (Terraform)

```bash
cd terraform/
terraform init
terraform plan -var="cluster_name=my-cluster"
terraform apply -var="cluster_name=my-cluster"
```

This deploys:
- Dedicated namespace (`chaos-engineering`)
- ServiceAccount with IRSA for Bedrock access
- ClusterRole with minimal permissions for chaos operations
- CronJob running experiments on schedule (default: Monday 2 AM)

### Docker Compose (local testing)

```bash
docker compose up
# Dashboard at http://localhost:8080
```

## Safety

- All experiments support `--dry-run` mode
- Experiment plans include `steady_state` checks
- DNS and network experiments auto-rollback after `duration_seconds`
- RBAC limits the runner to only required K8s operations
- Pod disruption budgets (PDBs) are respected by pod-kill

## License

MIT
