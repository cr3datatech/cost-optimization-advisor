import os
from datetime import date
import requests


_SEVERITY_EMOJI = {
    "high": ":red_circle:",
    "medium": ":large_yellow_circle:",
    "low": ":large_green_circle:",
}


def post_summary(anomalies: list[dict]) -> None:
    """Format and post a cost anomaly report to Slack via webhook."""
    webhook_url = os.environ["SLACK_WEBHOOK_URL"]
    today = date.today().isoformat()

    counts = {"high": 0, "medium": 0, "low": 0}
    for a in anomalies:
        counts[a.get("severity", "low")] += 1

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":moneybag: Cost Anomaly Report — {today}",
            },
        },
        {"type": "divider"},
    ]

    sorted_anomalies = sorted(
        anomalies,
        key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x.get("severity", "low"), 0),
        reverse=True,
    )

    for anomaly in sorted_anomalies:
        severity = anomaly.get("severity", "low")
        emoji = _SEVERITY_EMOJI.get(severity, ":white_circle:")
        narrative = anomaly.get("narrative", "")

        text_lines = [
            f"{emoji} *{anomaly['service']}* | {anomaly['region']} | Team: {anomaly['team_tag']}",
            f"• Actual: *${anomaly['cost_usd']:.2f}* vs baseline *${anomaly['baseline_usd']:.2f}* "
            f"(+{anomaly['deviation_pct']:.1f}%)",
        ]
        if narrative:
            text_lines.append(f"• {narrative}")

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(text_lines)},
            }
        )
        blocks.append({"type": "divider"})

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Total anomalies: {len(anomalies)} | "
                        f"High: {counts['high']} | "
                        f"Medium: {counts['medium']} | "
                        f"Low: {counts['low']}"
                    ),
                }
            ],
        }
    )

    payload = {"blocks": blocks}
    response = requests.post(webhook_url, json=payload, timeout=10)
    response.raise_for_status()
