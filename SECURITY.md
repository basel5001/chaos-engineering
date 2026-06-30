# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do NOT** open a public GitHub issue for security vulnerabilities.
2. Email the security team at security@xops.io with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Suggested fix (if any)

## Security Considerations

This toolkit operates with elevated Kubernetes privileges by design. When deploying:

### RBAC
- The chaos runner uses a ClusterRole with specific, limited permissions
- Avoid granting `cluster-admin` to the runner ServiceAccount
- Use separate namespaces for the runner and target workloads

### Network
- Latency injection requires `NET_ADMIN` capabilities (privileged pods)
- Limit which namespaces the runner can create privileged pods in via PodSecurityPolicies or OPA/Gatekeeper

### DNS
- DNS failure experiments modify the CoreDNS configmap
- Always set a `duration_seconds` limit to ensure automatic rollback
- Consider using a dedicated CoreDNS instance for chaos testing

### AWS Credentials
- Use IRSA (IAM Roles for Service Accounts) instead of static credentials
- Bedrock access should be scoped to `bedrock:InvokeModel` only
- Never store AWS credentials in manifests or environment files

### General
- Always test with `--dry-run` first
- Use pod disruption budgets (PDBs) on critical workloads
- Run chaos experiments during business hours with the team aware
- Have rollback procedures documented and tested

## Response Time

We aim to respond to security reports within 48 hours and provide a fix within 7 days for critical vulnerabilities.
