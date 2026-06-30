"""Network Latency Experiment - injects latency via tc in a privileged sidecar pod."""
import logging
import time
import uuid
from kubernetes import client, config

logger = logging.getLogger(__name__)

INJECTOR_IMAGE = "nicolaka/netshoot:latest"

INJECTOR_POD_TEMPLATE = {
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {},
    "spec": {
        "hostNetwork": True,
        "containers": [
            {
                "name": "latency-injector",
                "image": INJECTOR_IMAGE,
                "command": ["sh", "-c", ""],
                "securityContext": {"privileged": True, "capabilities": {"add": ["NET_ADMIN"]}},
            }
        ],
        "restartPolicy": "Never",
        "nodeSelector": {},
    },
}


def _build_tc_command(
    interface: str, latency_ms: int, jitter_ms: int, duration_seconds: int
) -> str:
    """Build tc commands to add and then remove latency."""
    add = f"tc qdisc add dev {interface} root netem delay {latency_ms}ms {jitter_ms}ms"
    remove = f"tc qdisc del dev {interface} root netem"
    return f"{add} && sleep {duration_seconds} && {remove}"


def _get_target_node(v1: client.CoreV1Api, namespace: str, label_selector: str) -> str | None:
    """Get the node name of the first matching running pod."""
    pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)
    running = [p for p in pods.items if p.status.phase == "Running"]
    if not running:
        return None
    return running[0].spec.node_name


def run(
    namespace: str,
    label_selector: str = "",
    interface: str = "eth0",
    latency_ms: int = 200,
    jitter_ms: int = 50,
    duration_seconds: int = 60,
    dry_run: bool = False,
) -> dict:
    """Inject network latency on the node hosting the target pod."""
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

    tc_cmd = _build_tc_command(interface, latency_ms, jitter_ms, duration_seconds)
    pod_name = f"chaos-latency-{uuid.uuid4().hex[:8]}"

    if dry_run:
        logger.info(
            f"[DRY RUN] Would deploy injector pod '{pod_name}' on node '{target_node}' "
            f"with command: {tc_cmd}"
        )
        return {
            "status": "completed",
            "dry_run": True,
            "node": target_node,
            "latency_ms": latency_ms,
            "jitter_ms": jitter_ms,
            "duration_seconds": duration_seconds,
            "pod_name": pod_name,
        }

    # Build the injector pod spec
    pod_manifest = _build_pod_manifest(pod_name, target_node, tc_cmd)

    logger.info(
        f"Deploying latency injector '{pod_name}' on node '{target_node}' — "
        f"{latency_ms}ms +/- {jitter_ms}ms for {duration_seconds}s"
    )
    v1.create_namespaced_pod(namespace, pod_manifest)

    # Wait for the injector pod to complete
    _wait_for_pod_completion(v1, namespace, pod_name, timeout=duration_seconds + 60)

    # Clean up the injector pod
    try:
        v1.delete_namespaced_pod(pod_name, namespace, grace_period_seconds=0)
    except client.ApiException:
        logger.warning(f"Could not clean up injector pod '{pod_name}'")

    return {
        "status": "completed",
        "dry_run": False,
        "node": target_node,
        "latency_ms": latency_ms,
        "jitter_ms": jitter_ms,
        "duration_seconds": duration_seconds,
        "pod_name": pod_name,
    }


def _build_pod_manifest(pod_name: str, node_name: str, command: str) -> dict:
    """Build the Kubernetes pod manifest for the latency injector."""
    import copy

    manifest = copy.deepcopy(INJECTOR_POD_TEMPLATE)
    manifest["metadata"] = {
        "name": pod_name,
        "labels": {"app": "chaos-latency-injector", "chaos.xops.io/experiment": "network-latency"},
    }
    manifest["spec"]["nodeSelector"] = {"kubernetes.io/hostname": node_name}
    manifest["spec"]["containers"][0]["command"] = ["sh", "-c", command]
    return manifest


def _wait_for_pod_completion(
    v1: client.CoreV1Api, namespace: str, pod_name: str, timeout: int = 120
) -> None:
    """Poll until the injector pod reaches Succeeded or Failed phase."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            pod = v1.read_namespaced_pod(pod_name, namespace)
            phase = pod.status.phase
            if phase in ("Succeeded", "Failed"):
                logger.info(f"Injector pod '{pod_name}' finished with phase: {phase}")
                return
        except client.ApiException as exc:
            logger.warning(f"Error polling injector pod: {exc.status}")
        time.sleep(5)
    logger.warning(f"Timed out waiting for injector pod '{pod_name}' after {timeout}s")
