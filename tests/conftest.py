"""Pytest configuration and shared fixtures."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_k8s_client():
    """Mock Kubernetes client for tests."""
    with patch("kubernetes.config.load_kube_config"), \
         patch("kubernetes.config.load_incluster_config", side_effect=Exception("not in cluster")):
        mock_v1 = MagicMock()
        with patch("kubernetes.client.CoreV1Api", return_value=mock_v1):
            yield mock_v1


@pytest.fixture
def sample_plan():
    """Return a sample experiment plan dict."""
    return {
        "apiVersion": "chaos.xops.io/v1alpha1",
        "kind": "ChaosExperiment",
        "metadata": {"name": "test-plan"},
        "spec": {
            "description": "Test plan for fixtures",
            "experiments": [
                {
                    "name": "kill-test",
                    "type": "pod-kill",
                    "namespace": "default",
                    "label_selector": "app=test",
                    "kill_count": 1,
                    "wait_seconds": 0,
                }
            ],
            "steady_state": {
                "check": "kubectl get pods",
                "expected": "1",
            },
        },
    }
