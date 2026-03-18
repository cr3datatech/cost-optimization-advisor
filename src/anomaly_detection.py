import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest


def detect_anomalies(df: pd.DataFrame) -> list[dict]:
    """Detect cost anomalies using z-score and IsolationForest."""
    if df.empty:
        return []

    df = df.copy()
    df = df.sort_values("date")

    zscore_anomalies = _zscore_anomalies(df)
    isolation_anomalies = _isolation_forest_anomalies(df)

    # Union by (date, service, region, team_tag) key
    seen = set()
    combined = []
    for a in zscore_anomalies + isolation_anomalies:
        key = (str(a["date"]), a["service"], a["region"], a["team_tag"])
        if key not in seen:
            seen.add(key)
            combined.append(a)

    combined.sort(key=lambda x: _severity_rank(x["severity"]), reverse=True)
    return combined


def _zscore_anomalies(df: pd.DataFrame) -> list[dict]:
    anomalies = []
    groups = df.groupby(["service", "region", "team_tag"])

    for (service, region, team_tag), group in groups:
        group = group.sort_values("date").copy()
        group["rolling_mean"] = group["cost_usd"].rolling(30, min_periods=1).mean()
        group["rolling_std"] = group["cost_usd"].rolling(30, min_periods=1).std().fillna(0)

        for _, row in group.iterrows():
            std = row["rolling_std"]
            mean = row["rolling_mean"]
            threshold = mean + 2 * std

            if std > 0 and row["cost_usd"] > threshold:
                deviation_pct = ((row["cost_usd"] - mean) / mean * 100) if mean > 0 else 0
                anomalies.append({
                    "service": service,
                    "region": region,
                    "account_id": row.get("account_id", ""),
                    "team_tag": team_tag,
                    "cost_usd": round(float(row["cost_usd"]), 4),
                    "baseline_usd": round(float(mean), 4),
                    "deviation_pct": round(float(deviation_pct), 2),
                    "severity": _severity(deviation_pct),
                    "date": str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"]),
                })

    return anomalies


def _isolation_forest_anomalies(df: pd.DataFrame) -> list[dict]:
    numeric = df[["cost_usd"]].copy().fillna(0)
    if len(numeric) < 10:
        return []

    clf = IsolationForest(contamination=0.05, random_state=42)
    preds = clf.fit_predict(numeric)

    anomaly_rows = df[preds == -1].copy()
    anomalies = []

    for _, row in anomaly_rows.iterrows():
        service = row.get("service", "")
        region = row.get("region", "")
        team_tag = row.get("team_tag", "")

        group_mean = df[
            (df["service"] == service) & (df["region"] == region) & (df["team_tag"] == team_tag)
        ]["cost_usd"].mean()

        if pd.isna(group_mean) or group_mean == 0:
            group_mean = df["cost_usd"].mean()

        deviation_pct = ((row["cost_usd"] - group_mean) / group_mean * 100) if group_mean > 0 else 0

        anomalies.append({
            "service": service,
            "region": region,
            "account_id": row.get("account_id", ""),
            "team_tag": team_tag,
            "cost_usd": round(float(row["cost_usd"]), 4),
            "baseline_usd": round(float(group_mean), 4),
            "deviation_pct": round(float(deviation_pct), 2),
            "severity": _severity(deviation_pct),
            "date": str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"]),
        })

    return anomalies


def _severity(deviation_pct: float) -> str:
    if deviation_pct > 100:
        return "high"
    elif deviation_pct > 50:
        return "medium"
    else:
        return "low"


def _severity_rank(severity: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(severity, 0)
