"""Disk Fill Experiment - fills disk on a target node using a temporary pod with dd/fallocate."""
import logging
import time
import uuid
from kubernetes import client, config

logger = logging.getLogger(__name__)

BUSYBOX_IMAGE = "busybox:1.36"


def _get_target_node(v1: client.CoreV1Api, namespace: str, label_selector: str) -> str | None:
    """Get the node name of the first matching running pod."""
    pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)
    running = [p for p in pods.items if p.status.phase == "Running"]
    if not running:
        return None
    return running[0].spec.node_name


def _build_disk_fill_pod(
    pod_name: str,
    node_name: str,
    fill_size_mb: int,
    fill_path: str,
    duration_seconds: int,
) -> dict:
    """Build a pod manifest that fills disk and cleans up after duration."""
    fill_file = f"{fill_path}/chaos-disk-fill-{pod_name}.dat"
    cmd = (
        f"dd if=/dev/zero of={fill_file} bs=1M count={fill_size_mb} "
        f"&& echo 'Disk filled with {fill_size_mb}MB' "
        f"&& sleep {duration_seconds} "
        f"&& rm -f {fill_file} "
        f"&& echo 'Cleaned up'"
    )
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "labels": {
                "app": "chaos-disk-fill",
                "chaos.xops.io/experiment": "disk-fill",
            },
        },
        "spec": {
            "containers": [
                {
                    "name": "disk-filler",
                    "image": BUSYBOX_IMAGE,
                    "command": ["sh", "-c", cmd],
                    "volumeMounts": [
                        {"name": "host-disk", "mountPath": fill_path},
                    ],
                }
            ],
            "volumes": [
                {
                    "name": "host-disk",
                    "hostPath": {"path": fill_path, "type": "DirectoryOrCreate"},
                }
            ],
            "nodeSelector": {"kubernetes.io/hostname": node_name},
            "restartPolicy": "Never",
        },
    }


def _wait_for_completion(
    v1: client.CoreV1Api, namespace: str, pod_name: str, timeout: int
) -> str:
    """Wait for the disk-fill pod to complete."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            pod = v1.read_namespaced_pod(pod_name, namespace)
            phase = pod.status.phase
            if phase in ("Succeeded", "Failed"):
                return phase
        except client.ApiException as exc:
            logger.warning(f"Error polling disk-fill pod: {exc.status}")
        time.sleep(5)
    return "Timeout"


def run(
    namespace: str,
    label_selector: str = "",
    fill_size_mb: int = 512,
    fill_path: str = "/tmp/chaos-disk",
    duration_seconds: int = 60,
    dry_run: bool = False,
) -> dict:
    """Fill disk on the node hosting the target workload."""
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

    pod_name = f"chaos-disk-fill-{uuid.uuid4().hex[:8]}"

    if dry_run:
        logger.info(
            f"[DRY RUN] Would fill {fill_size_mb}MB at '{fill_path}' on node '{target_node}' "
            f"for {duration_seconds}s"
        )
        return {
            "status": "completed",
            "dry_run": True,
            "node": target_node,
            "fill_size_mb": fill_size_mb,
            "fill_path": fill_path,
            "duration_seconds": duration_seconds,
            "pod_name": pod_name,
        }

    pod_manifest = _build_disk_fill_pod(pod_name, target_node, fill_size_mb, fill_path, duration_seconds)

    logger.info(
        f"Deploying disk-fill pod '{pod_name}' on node '{target_node}' — "
        f"{fill_size_mb}MB at '{fill_path}' for {duration_seconds}s"
    )
    v1.create_namespaced_pod(namespace, pod_manifest)

    final_phase = _wait_for_completion(v1, namespace, pod_name, timeout=duration_seconds + 120)

    # Cleanup
    try:
        v1.delete_namespaced_pod(pod_name, namespace, grace_period_seconds=0)
    except client.ApiException:
        logger.warning(f"Could not clean up disk-fill pod '{pod_name}'")

    return {
        "status": "completed" if final_phase == "Succeeded" else "failed",
        "dry_run": False,
        "node": target_node,
        "fill_size_mb": fill_size_mb,
        "fill_path": fill_path,
        "duration_seconds": duration_seconds,
        "pod_name": pod_name,
        "final_phase": final_phase,
    }
