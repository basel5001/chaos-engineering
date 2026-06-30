"""CPU Stress Experiment - deploys a stress-ng pod to consume CPU on a target node."""
import logging
import time
import uuid
from kubernetes import client, config

logger = logging.getLogger(__name__)

STRESS_IMAGE = "alexeiled/stress-ng:latest"


def _get_target_node(v1: client.CoreV1Api, namespace: str, label_selector: str) -> str | None:
    """Get the node name of the first matching running pod."""
    pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)
    running = [p for p in pods.items if p.status.phase == "Running"]
    if not running:
        return None
    return running[0].spec.node_name


def _build_stress_pod(
    pod_name: str, node_name: str, cpu_workers: int, cpu_percent: int, duration_seconds: int
) -> dict:
    """Build the stress-ng pod manifest."""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "labels": {
                "app": "chaos-cpu-stress",
                "chaos.xops.io/experiment": "cpu-stress",
            },
        },
        "spec": {
            "containers": [
                {
                    "name": "stress",
                    "image": STRESS_IMAGE,
                    "args": [
                        "--cpu",
                        str(cpu_workers),
                        "--cpu-load",
                        str(cpu_percent),
                        "--timeout",
                        f"{duration_seconds}s",
                        "--metrics-brief",
                    ],
                    "resources": {
                        "requests": {"cpu": f"{cpu_workers * 100}m"},
                        "limits": {"cpu": str(cpu_workers)},
                    },
                }
            ],
            "nodeSelector": {"kubernetes.io/hostname": node_name},
            "restartPolicy": "Never",
        },
    }


def _wait_for_completion(
    v1: client.CoreV1Api, namespace: str, pod_name: str, timeout: int
) -> str:
    """Wait for the stress pod to complete. Returns final phase."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            pod = v1.read_namespaced_pod(pod_name, namespace)
            phase = pod.status.phase
            if phase in ("Succeeded", "Failed"):
                return phase
        except client.ApiException as exc:
            logger.warning(f"Error polling stress pod: {exc.status}")
        time.sleep(5)
    return "Timeout"


def run(
    namespace: str,
    label_selector: str = "",
    cpu_workers: int = 2,
    cpu_percent: int = 80,
    duration_seconds: int = 60,
    dry_run: bool = False,
) -> dict:
    """Deploy a stress-ng pod on the same node as the target workload."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    v1 = client.CoreV1Api()

    target_node = _get_target_node(v1, namespace, label_selector)
    if target_node is None:
        return {
            "status": "skipped",
            "reason": "no running pods match selector",
            "namespace": namespace,
        }

    pod_name = f"chaos-cpu-stress-{uuid.uuid4().hex[:8]}"

    if dry_run:
        logger.info(
            f"[DRY RUN] Would deploy stress pod '{pod_name}' on node '{target_node}' — "
            f"{cpu_workers} workers at {cpu_percent}% for {duration_seconds}s"
        )
        return {
            "status": "completed",
            "dry_run": True,
            "node": target_node,
            "cpu_workers": cpu_workers,
            "cpu_percent": cpu_percent,
            "duration_seconds": duration_seconds,
            "pod_name": pod_name,
        }

    pod_manifest = _build_stress_pod(pod_name, target_node, cpu_workers, cpu_percent, duration_seconds)

    logger.info(
        f"Deploying CPU stress pod '{pod_name}' on node '{target_node}' — "
        f"{cpu_workers} workers at {cpu_percent}% for {duration_seconds}s"
    )
    v1.create_namespaced_pod(namespace, pod_manifest)

    final_phase = _wait_for_completion(v1, namespace, pod_name, timeout=duration_seconds + 60)

    # Retrieve logs before cleanup
    logs = ""
    try:
        logs = v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=50)
    except client.ApiException:
        logger.warning(f"Could not retrieve logs from stress pod '{pod_name}'")

    # Cleanup
    try:
        v1.delete_namespaced_pod(pod_name, namespace, grace_period_seconds=0)
    except client.ApiException:
        logger.warning(f"Could not clean up stress pod '{pod_name}'")

    return {
        "status": "completed" if final_phase == "Succeeded" else "failed",
        "dry_run": False,
        "node": target_node,
        "cpu_workers": cpu_workers,
        "cpu_percent": cpu_percent,
        "duration_seconds": duration_seconds,
        "pod_name": pod_name,
        "final_phase": final_phase,
        "logs": logs,
    }
