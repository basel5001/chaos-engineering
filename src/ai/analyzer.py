"""AWS Bedrock AI Analyzer for chaos experiment results."""
import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
MAX_TOKENS = 4096


def _get_bedrock_client(region: str | None = None) -> Any:
    """Create a Bedrock Runtime client."""
    return boto3.client(
        "bedrock-runtime",
        region_name=region or DEFAULT_REGION,
    )


def _invoke_model(prompt: str, system: str = "", model_id: str = "") -> str:
    """Invoke a Bedrock model and return the text response."""
    bedrock = _get_bedrock_client()
    model = model_id or DEFAULT_MODEL_ID

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    if system:
        body["system"] = system

    response = bedrock.invoke_model(
        modelId=model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )

    result = json.loads(response["body"].read())
    # Claude response format
    if "content" in result and isinstance(result["content"], list):
        return "".join(
            block.get("text", "") for block in result["content"] if block.get("type") == "text"
        )
    # Fallback for other models
    return result.get("completion", result.get("output", str(result)))


def analyze_results(results: list[dict]) -> str:
    """AI analyzes chaos experiment results, identifies weaknesses, and suggests hardening.

    Args:
        results: List of experiment result dicts from the orchestrator.

    Returns:
        Markdown-formatted analysis string.
    """
    system = (
        "You are a senior Site Reliability Engineer specializing in chaos engineering "
        "and resilience testing. Analyze the experiment results and provide actionable "
        "insights. Format your response in Markdown."
    )

    prompt = f"""Analyze these chaos engineering experiment results and provide:

1. **Executive Summary** - Overall resilience assessment (1-2 sentences)
2. **Findings** - What each experiment revealed about system resilience
3. **Weaknesses Identified** - Specific vulnerabilities discovered
4. **Risk Assessment** - Severity rating (Critical/High/Medium/Low) for each finding
5. **Hardening Recommendations** - Concrete steps to improve resilience
6. **Follow-up Experiments** - Additional chaos tests to run next

Experiment Results:
```json
{json.dumps(results, indent=2, default=str)}
```"""

    try:
        return _invoke_model(prompt, system=system)
    except Exception as e:
        logger.error(f"Bedrock analysis failed: {e}")
        return f"**AI Analysis unavailable:** {e}"


def predict_blast_radius(experiment: dict, infra: dict) -> str:
    """Predict the impact of a proposed chaos experiment on the infrastructure.

    Args:
        experiment: Proposed experiment configuration dict.
        infra: Infrastructure description dict (services, dependencies, replicas, etc.).

    Returns:
        Markdown-formatted blast radius prediction.
    """
    system = (
        "You are a chaos engineering expert. Predict the blast radius of a proposed "
        "experiment given the infrastructure description. Be specific about which "
        "services, users, and SLOs may be affected."
    )

    prompt = f"""Predict the blast radius for this proposed chaos experiment:

**Proposed Experiment:**
```json
{json.dumps(experiment, indent=2, default=str)}
```

**Infrastructure Description:**
```json
{json.dumps(infra, indent=2, default=str)}
```

Provide:
1. **Affected Services** - Which services will be directly and indirectly impacted
2. **User Impact** - Expected impact on end users (latency, errors, outage)
3. **SLO Impact** - Which SLOs are at risk and estimated impact
4. **Cascade Risk** - Probability and description of cascading failures
5. **Mitigation** - Steps to limit blast radius during the experiment
6. **Go/No-Go Recommendation** - Whether to proceed and under what conditions"""

    try:
        return _invoke_model(prompt, system=system)
    except Exception as e:
        logger.error(f"Bedrock blast radius prediction failed: {e}")
        return f"**Blast radius prediction unavailable:** {e}"


def suggest_experiments(service_description: str) -> list[dict]:
    """AI suggests chaos experiments appropriate for the described service.

    Args:
        service_description: Natural-language description of the service architecture.

    Returns:
        List of suggested experiment configuration dicts.
    """
    system = (
        "You are a chaos engineering expert. Suggest specific, actionable chaos "
        "experiments based on the service description. Return a JSON array of "
        "experiment configurations compatible with the chaos-engineering toolkit."
    )

    prompt = f"""Based on this service description, suggest chaos experiments to test resilience:

**Service Description:**
{service_description}

Return a JSON array where each element has:
- "name": descriptive experiment name
- "type": one of "pod-kill", "network-latency", "cpu-stress", "disk-fill", "dns-failure"
- "namespace": target Kubernetes namespace
- "label_selector": Kubernetes label selector
- "rationale": why this experiment is valuable
- Plus type-specific parameters (kill_count, latency_ms, cpu_percent, etc.)

Return ONLY the JSON array, no other text."""

    try:
        raw = _invoke_model(prompt, system=system)
        # Extract JSON from the response (handle markdown code blocks)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            cleaned = "\n".join(json_lines)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI suggestions as JSON: {e}")
        return [{"error": "Failed to parse AI response", "raw_response": raw}]
    except Exception as e:
        logger.error(f"Bedrock suggestion failed: {e}")
        return [{"error": str(e)}]
