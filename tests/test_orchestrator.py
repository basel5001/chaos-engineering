"""Tests for the chaos engineering orchestrator."""
import json
import pytest
from unittest.mock import patch, MagicMock
from dataclasses import asdict

from src.runner.orchestrator import (
    ExperimentResult,
    ExperimentPlan,
    run_experiment,
    generate_report,
    load_plan_from_yaml,
    results_to_dicts,
)


# ---------------------------------------------------------------------------
# ExperimentResult dataclass
# ---------------------------------------------------------------------------

class TestExperimentResult:
    def test_creation(self):
        r = ExperimentResult(
            name="test-kill",
            type="pod-kill",
            namespace="default",
            status="completed",
            start_time="2025-01-01T00:00:00",
            end_time="2025-01-01T00:00:05",
            duration_seconds=5.0,
        )
        assert r.name == "test-kill"
        assert r.status == "completed"
        assert r.details == {}
        assert r.ai_analysis == ""

    def test_with_details(self):
        r = ExperimentResult(
            name="net-test",
            type="network-latency",
            namespace="staging",
            status="failed",
            start_time="2025-01-01T00:00:00",
            end_time="2025-01-01T00:01:00",
            duration_seconds=60.0,
            details={"latency_ms": 200, "error": "timeout"},
            ai_analysis="System is fragile under latency.",
        )
        assert r.details["latency_ms"] == 200
        assert "fragile" in r.ai_analysis

    def test_to_dict(self):
        r = ExperimentResult(
            name="x", type="pod-kill", namespace="n", status="completed",
            start_time="t0", end_time="t1", duration_seconds=1.0,
        )
        d = asdict(r)
        assert isinstance(d, dict)
        assert d["name"] == "x"
        assert d["metrics_before"] == {}


# ---------------------------------------------------------------------------
# ExperimentPlan dataclass
# ---------------------------------------------------------------------------

class TestExperimentPlan:
    def test_creation(self):
        plan = ExperimentPlan(
            name="test-plan",
            description="A test",
            experiments=[{"type": "pod-kill", "namespace": "default", "kill_count": 1}],
        )
        assert plan.name == "test-plan"
        assert len(plan.experiments) == 1

    def test_defaults(self):
        plan = ExperimentPlan(name="p", description="d", experiments=[])
        assert plan.steady_state_check == {}
        assert plan.rollback == {}


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_report_contains_header(self):
        results = [
            ExperimentResult(
                name="kill-test", type="pod-kill", namespace="default",
                status="completed", start_time="t0", end_time="t1",
                duration_seconds=2.5,
                details={"killed": [{"name": "pod-1"}]},
            ),
            ExperimentResult(
                name="net-test", type="network-latency", namespace="staging",
                status="failed", start_time="t0", end_time="t1",
                duration_seconds=60.0,
                details={"error": "pod scheduling failed"},
            ),
        ]
        md = generate_report(results)
        assert "# Chaos Engineering Report" in md
        assert "**Experiments:** 2" in md
        assert "**Passed:** 1" in md
        assert "**Failed:** 1" in md

    def test_report_table(self):
        results = [
            ExperimentResult(
                name="t1", type="pod-kill", namespace="default",
                status="completed", start_time="a", end_time="b",
                duration_seconds=1.0,
            ),
        ]
        md = generate_report(results)
        assert "| t1 | pod-kill | default | completed | 1.0s |" in md

    def test_report_ai_analysis(self):
        results = [
            ExperimentResult(
                name="t1", type="pod-kill", namespace="default",
                status="completed", start_time="a", end_time="b",
                duration_seconds=1.0,
                ai_analysis="The system is resilient.",
            ),
        ]
        md = generate_report(results)
        assert "**AI Analysis:**" in md
        assert "The system is resilient." in md

    def test_empty_results(self):
        md = generate_report([])
        assert "**Experiments:** 0" in md
        assert "**Passed:** 0" in md


# ---------------------------------------------------------------------------
# run_experiment (mocked)
# ---------------------------------------------------------------------------

class TestRunExperiment:
    @patch("src.experiments.pod_kill.run")
    def test_pod_kill_success(self, mock_run):
        mock_run.return_value = {
            "status": "completed",
            "killed": [{"name": "pod-1", "dry_run": False}],
        }
        plan = ExperimentPlan(
            name="test",
            description="test plan",
            experiments=[
                {"type": "pod-kill", "name": "kill-test", "namespace": "default", "kill_count": 1}
            ],
        )
        results = run_experiment(plan, dry_run=True)
        assert len(results) == 1
        assert results[0].status == "completed"
        assert results[0].name == "kill-test"

    @patch("src.experiments.pod_kill.run")
    def test_experiment_failure(self, mock_run):
        mock_run.side_effect = RuntimeError("k8s connection refused")
        plan = ExperimentPlan(
            name="test",
            description="test plan",
            experiments=[
                {"type": "pod-kill", "name": "kill-fail", "namespace": "default"}
            ],
        )
        results = run_experiment(plan, dry_run=True)
        assert len(results) == 1
        assert results[0].status == "failed"
        assert "k8s connection refused" in results[0].details["error"]

    def test_unknown_experiment_type(self):
        plan = ExperimentPlan(
            name="test",
            description="test plan",
            experiments=[
                {"type": "unknown-chaos", "name": "bad-type", "namespace": "default"}
            ],
        )
        results = run_experiment(plan, dry_run=True)
        assert len(results) == 0  # unknown types are skipped

    @patch("src.experiments.pod_kill.run")
    @patch("src.experiments.network_latency.run")
    def test_multiple_experiments(self, mock_net, mock_kill):
        mock_kill.return_value = {"status": "completed", "killed": []}
        mock_net.return_value = {"status": "completed", "latency_ms": 200}
        plan = ExperimentPlan(
            name="multi",
            description="multiple experiments",
            experiments=[
                {"type": "pod-kill", "name": "kill-1", "namespace": "default", "wait_seconds": 0},
                {"type": "network-latency", "name": "net-1", "namespace": "default", "wait_seconds": 0},
            ],
        )
        results = run_experiment(plan, dry_run=True)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# load_plan_from_yaml
# ---------------------------------------------------------------------------

class TestLoadPlan:
    def test_load_from_yaml(self, tmp_path):
        yaml_content = """
apiVersion: chaos.xops.io/v1alpha1
kind: ChaosExperiment
metadata:
  name: test-plan
spec:
  description: "Test plan for unit tests"
  experiments:
    - name: kill-test
      type: pod-kill
      namespace: default
      label_selector: "app=web"
      kill_count: 1
  steady_state:
    check: "kubectl get pods"
    expected: "3"
"""
        yaml_file = tmp_path / "test-plan.yml"
        yaml_file.write_text(yaml_content)

        plan = load_plan_from_yaml(str(yaml_file))
        assert plan.name == "test-plan"
        assert plan.description == "Test plan for unit tests"
        assert len(plan.experiments) == 1
        assert plan.experiments[0]["type"] == "pod-kill"
        assert plan.steady_state_check["expected"] == "3"


# ---------------------------------------------------------------------------
# results_to_dicts
# ---------------------------------------------------------------------------

class TestResultsToDicts:
    def test_conversion(self):
        results = [
            ExperimentResult(
                name="t1", type="pod-kill", namespace="ns",
                status="completed", start_time="a", end_time="b",
                duration_seconds=1.0,
            ),
        ]
        dicts = results_to_dicts(results)
        assert isinstance(dicts, list)
        assert isinstance(dicts[0], dict)
        assert dicts[0]["name"] == "t1"
