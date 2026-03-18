import os
from pathlib import Path
from typing import Optional
import anthropic


_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "cost_narrative.txt"
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def generate_recommendation(anomaly: dict) -> str:
    """Call Claude to generate a human-readable cost narrative for an anomaly."""
    template = _PROMPT_PATH.read_text()
    prompt = template.format(
        service=anomaly["service"],
        region=anomaly["region"],
        team_tag=anomaly["team_tag"],
        cost_usd=anomaly["cost_usd"],
        baseline_usd=anomaly["baseline_usd"],
        deviation_pct=anomaly["deviation_pct"],
        date=anomaly["date"],
    )

    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    return next(
        (block.text for block in response.content if block.type == "text"),
        "",
    )
