"""Pod Kill Experiment - randomly kills pods in a namespace."""
import random
import logging
from kubernetes import client, config

logger = logging.getLogger(__name__)


def run(namespace: str, label_selector: str = "", kill_count: int = 1, dry_run: bool = False) -> dict:
    """Kill random pods in a namespace."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)
    running = [p for p in pods.items if p.status.phase == "Running"]

    if not running:
        return {"status": "skipped", "reason": "no running pods found", "killed": []}

    targets = random.sample(running, min(kill_count, len(running)))
    killed = []

    for pod in targets:
        name = pod.metadata.name
        if dry_run:
            logger.info(f"[DRY RUN] Would kill pod: {name}")
            killed.append({"name": name, "dry_run": True})
        else:
            logger.info(f"Killing pod: {name}")
            v1.delete_namespaced_pod(name, namespace, grace_period_seconds=0)
            killed.append({"name": name, "dry_run": False})

    return {"status": "completed", "killed": killed, "namespace": namespace}
