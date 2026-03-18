import os
from pathlib import Path
from typing import Optional
import openai


_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "cost_narrative.txt"
_client: Optional[openai.OpenAI] = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def generate_recommendation(anomaly: dict) -> str:
    """Call OpenAI to generate a human-readable cost narrative for an anomaly."""
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
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content or ""
