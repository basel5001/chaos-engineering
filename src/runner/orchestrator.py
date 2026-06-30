"""Chaos Engineering Orchestrator."""
import json
import time
import logging
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExperimentResult:
    name: str
    type: str
    namespace: str
    status: str  # completed, failed, skipped
    start_time: str
    end_time: str
    duration_seconds: float
    details: dict = field(default_factory=dict)
    metrics_before: dict = field(default_factory=dict)
    metrics_after: dict = field(default_factory=dict)
    ai_analysis: str = ""


@dataclass
class ExperimentPlan:
    name: str
    description: str
    experiments: list[dict]
    steady_state_check: dict = field(default_factory=dict)
    rollback: dict = field(default_factory=dict)


def run_experiment(plan: ExperimentPlan, dry_run: bool = False) -> list[ExperimentResult]:
    """Run a chaos experiment plan."""
    from src.experiments import pod_kill, network_latency, cpu_stress, dns_failure

    experiment_map = {
        "pod-kill": pod_kill.run,
        "network-latency": network_latency.run,
        "cpu-stress": cpu_stress.run,
        "dns-failure": dns_failure.run,
    }

    results = []
    for exp in plan.experiments:
        exp_type = exp["type"]
        runner = experiment_map.get(exp_type)
        if not runner:
            logger.error(f"Unknown experiment type: {exp_type}")
            continue

        start = datetime.utcnow()
        logger.info(f"Running experiment: {exp.get('name', exp_type)}")

        try:
            params = {k: v for k, v in exp.items() if k not in ("type", "name")}
            params["dry_run"] = dry_run
            details = runner(**params)
            status = details.get("status", "completed")
        except Exception as e:
            details = {"error": str(e)}
            status = "failed"
            logger.error(f"Experiment failed: {e}")

        end = datetime.utcnow()
        results.append(ExperimentResult(
            name=exp.get("name", exp_type),
            type=exp_type,
            namespace=exp.get("namespace", "default"),
            status=status,
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            duration_seconds=(end - start).total_seconds(),
            details=details,
        ))

        # Wait between experiments
        wait = exp.get("wait_seconds", 10)
        if not dry_run and wait > 0:
            logger.info(f"Waiting {wait}s before next experiment...")
            time.sleep(wait)

    return results


def generate_report(results: list[ExperimentResult]) -> str:
    """Generate a markdown report from experiment results."""
    md = "# Chaos Engineering Report\n\n"
    md += f"**Date:** {datetime.utcnow().isoformat()}\n"
    md += f"**Experiments:** {len(results)}\n"
    md += f"**Passed:** {sum(1 for r in results if r.status == 'completed')}\n"
    md += f"**Failed:** {sum(1 for r in results if r.status == 'failed')}\n\n"

    md += "## Results\n\n"
    md += "| Experiment | Type | Namespace | Status | Duration |\n"
    md += "|------------|------|-----------|--------|----------|\n"
    for r in results:
        md += f"| {r.name} | {r.type} | {r.namespace} | {r.status} | {r.duration_seconds:.1f}s |\n"

    md += "\n## Details\n\n"
    for r in results:
        md += f"### {r.name}\n"
        md += f"- **Type:** {r.type}\n"
        md += f"- **Status:** {r.status}\n"
        md += f"- **Duration:** {r.duration_seconds:.1f}s\n"
        md += f"- **Details:** `{json.dumps(r.details)}`\n"
        if r.ai_analysis:
            md += f"\n**AI Analysis:**\n{r.ai_analysis}\n"
        md += "\n"

    return md


def load_plan_from_yaml(path: str) -> ExperimentPlan:
    """Load an experiment plan from a YAML file (CRD-style manifest)."""
    import yaml

    with open(path) as f:
        doc = yaml.safe_load(f)

    spec = doc.get("spec", doc)
    metadata = doc.get("metadata", {})

    experiments_raw = spec.get("experiments", [])
    experiments = []
    for exp in experiments_raw:
        # Normalise keys: YAML uses underscores, but keep both
        experiments.append({k.replace("-", "_"): v for k, v in exp.items()})

    return ExperimentPlan(
        name=metadata.get("name", spec.get("name", "unnamed")),
        description=spec.get("description", ""),
        experiments=experiments,
        steady_state_check=spec.get("steady_state", {}),
        rollback=spec.get("rollback", {}),
    )


def results_to_dicts(results: list[ExperimentResult]) -> list[dict]:
    """Convert a list of ExperimentResult dataclasses to plain dicts."""
    return [asdict(r) for r in results]
