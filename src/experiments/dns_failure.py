"""DNS Failure Experiment - patches CoreDNS configmap to simulate DNS resolution failures."""
import copy
import logging
import time
from kubernetes import client, config

logger = logging.getLogger(__name__)

COREDNS_CONFIGMAP = "coredns"
COREDNS_NAMESPACE = "kube-system"
COREDNS_KEY = "Corefile"

# Template block injected into the Corefile to black-hole specific domains
FAILURE_BLOCK_TEMPLATE = """
# --- chaos-dns-failure-start ---
{domain}:53 {{
    errors
    health
    template IN A {domain} {{
        rcode SERVFAIL
    }}
}}
# --- chaos-dns-failure-end ---
"""


def _load_kube() -> client.CoreV1Api:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CoreV1Api()


def _get_corefile(v1: client.CoreV1Api) -> tuple[client.V1ConfigMap, str]:
    """Return the CoreDNS configmap and its Corefile content."""
    cm = v1.read_namespaced_config_map(COREDNS_CONFIGMAP, COREDNS_NAMESPACE)
    corefile = cm.data.get(COREDNS_KEY, "")
    return cm, corefile


def _inject_failure(corefile: str, domains: list[str]) -> str:
    """Inject SERVFAIL blocks for the given domains into the Corefile."""
    blocks = "".join(FAILURE_BLOCK_TEMPLATE.format(domain=d) for d in domains)
    return corefile + blocks


def _remove_failure(corefile: str) -> str:
    """Remove all injected chaos blocks from the Corefile."""
    lines = corefile.splitlines(keepends=True)
    result: list[str] = []
    skip = False
    for line in lines:
        if "chaos-dns-failure-start" in line:
            skip = True
            continue
        if "chaos-dns-failure-end" in line:
            skip = False
            continue
        if not skip:
            result.append(line)
    return "".join(result)


def _restart_coredns(v1: client.CoreV1Api) -> None:
    """Delete CoreDNS pods to pick up configmap changes."""
    apps = client.AppsV1Api()
    try:
        # Trigger a rollout restart by patching the deployment annotation
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {"chaos.xops.io/restartedAt": now}
                    }
                }
            }
        }
        apps.patch_namespaced_deployment("coredns", COREDNS_NAMESPACE, body)
        logger.info("Triggered CoreDNS rollout restart")
    except client.ApiException as exc:
        logger.warning(f"Could not restart CoreDNS deployment: {exc.status}")


def run(
    namespace: str = "kube-system",
    domains: list[str] | None = None,
    duration_seconds: int = 60,
    dry_run: bool = False,
    label_selector: str = "",
) -> dict:
    """Inject DNS failures for specific domains by patching CoreDNS.

    Args:
        namespace: Not used directly (CoreDNS lives in kube-system), kept for interface compat.
        domains: List of domains to fail resolution for.
        duration_seconds: How long to keep the failure active before rollback.
        dry_run: If True, only log what would happen.
        label_selector: Unused, kept for interface compatibility.
    """
    if not domains:
        domains = ["example.com"]

    v1 = _load_kube()

    # Read original Corefile
    cm, original_corefile = _get_corefile(v1)
    patched_corefile = _inject_failure(original_corefile, domains)

    if dry_run:
        logger.info(
            f"[DRY RUN] Would patch CoreDNS to fail DNS for {domains} for {duration_seconds}s"
        )
        return {
            "status": "completed",
            "dry_run": True,
            "domains": domains,
            "duration_seconds": duration_seconds,
            "patched_corefile_preview": patched_corefile[:500],
        }

    # --- Apply failure ---
    logger.info(f"Patching CoreDNS to fail DNS for: {domains}")
    cm_patch = copy.deepcopy(cm)
    cm_patch.data[COREDNS_KEY] = patched_corefile
    v1.replace_namespaced_config_map(COREDNS_CONFIGMAP, COREDNS_NAMESPACE, cm_patch)
    _restart_coredns(v1)

    logger.info(f"DNS failure active — waiting {duration_seconds}s before rollback")
    time.sleep(duration_seconds)

    # --- Rollback ---
    logger.info("Rolling back CoreDNS configmap to original")
    cm_rollback = copy.deepcopy(cm)
    cm_rollback.data[COREDNS_KEY] = original_corefile
    v1.replace_namespaced_config_map(COREDNS_CONFIGMAP, COREDNS_NAMESPACE, cm_rollback)
    _restart_coredns(v1)

    return {
        "status": "completed",
        "dry_run": False,
        "domains": domains,
        "duration_seconds": duration_seconds,
        "namespace": namespace,
    }
