"""Tests for the AI analyzer module."""
import json
import pytest
from unittest.mock import patch, MagicMock

from src.ai.analyzer import analyze_results, predict_blast_radius, suggest_experiments


class TestAnalyzeResults:
    @patch("src.ai.analyzer._invoke_model")
    def test_successful_analysis(self, mock_invoke):
        mock_invoke.return_value = "## Findings\n\nThe system handled pod kills well."
        results = [
            {
                "name": "kill-test",
                "type": "pod-kill",
                "status": "completed",
                "duration_seconds": 5.0,
                "details": {"killed": [{"name": "pod-1"}]},
            }
        ]
        analysis = analyze_results(results)
        assert "Findings" in analysis
        mock_invoke.assert_called_once()

    @patch("src.ai.analyzer._invoke_model")
    def test_analysis_failure(self, mock_invoke):
        mock_invoke.side_effect = RuntimeError("Bedrock unavailable")
        results = [{"name": "test", "status": "completed"}]
        analysis = analyze_results(results)
        assert "unavailable" in analysis.lower()


class TestPredictBlastRadius:
    @patch("src.ai.analyzer._invoke_model")
    def test_successful_prediction(self, mock_invoke):
        mock_invoke.return_value = "## Affected Services\n\n- frontend\n- API gateway"
        experiment = {"type": "pod-kill", "namespace": "default", "kill_count": 3}
        infra = {"services": ["frontend", "backend", "database"], "replicas": {"frontend": 3}}
        result = predict_blast_radius(experiment, infra)
        assert "Affected" in result

    @patch("src.ai.analyzer._invoke_model")
    def test_prediction_failure(self, mock_invoke):
        mock_invoke.side_effect = Exception("timeout")
        result = predict_blast_radius({}, {})
        assert "unavailable" in result.lower()


class TestSuggestExperiments:
    @patch("src.ai.analyzer._invoke_model")
    def test_successful_suggestions(self, mock_invoke):
        suggestions = [
            {"name": "kill-frontend", "type": "pod-kill", "namespace": "default"},
            {"name": "latency-db", "type": "network-latency", "namespace": "default"},
        ]
        mock_invoke.return_value = json.dumps(suggestions)
        result = suggest_experiments("A web app with 3 frontend pods and a PostgreSQL database")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["type"] == "pod-kill"

    @patch("src.ai.analyzer._invoke_model")
    def test_json_in_code_block(self, mock_invoke):
        suggestions = [{"name": "test", "type": "cpu-stress"}]
        mock_invoke.return_value = f"```json\n{json.dumps(suggestions)}\n```"
        result = suggest_experiments("A simple service")
        assert isinstance(result, list)
        assert result[0]["name"] == "test"

    @patch("src.ai.analyzer._invoke_model")
    def test_suggestion_failure(self, mock_invoke):
        mock_invoke.side_effect = RuntimeError("Bedrock quota exceeded")
        result = suggest_experiments("anything")
        assert isinstance(result, list)
        assert "error" in result[0]
