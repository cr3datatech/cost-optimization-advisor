# Cost Optimization AI Advisor

An AWS Lambda function that ingests billing data, detects cost anomalies, generates human-readable recommendations via Claude, and posts them to Slack daily.

---

## What it does

The advisor pulls the latest AWS Cost & Usage Report CSV from S3, runs statistical anomaly detection (z-score + Isolation Forest), calls Claude to generate a plain-English narrative for each anomaly, and posts a formatted summary to a Slack channel. It runs daily via EventBridge with no human intervention required.

---

## Architecture

```
EventBridge (daily cron)
        │
        ▼
  Lambda handler
        │
        ├─► S3 (billing CSVs) ──► ingestion.py ──► DataFrame
        │
        ├─► anomaly_detection.py (z-score + IsolationForest)
        │
        ├─► Anthropic Claude API ──► llm_advisor.py ──► narratives
        │
        └─► Slack Webhook ──► slack_notifier.py ──► Slack channel
```

---

## Prerequisites

- AWS account with S3 bucket containing AWS Cost & Usage Report CSVs
- Anthropic API key (https://console.anthropic.com)
- Slack Incoming Webhook URL (create via Slack App settings)
- Python 3.12

---

## Local development setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd cost-optimization-advisor

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env file
cat > .env <<EOF
AWS_BILLING_BUCKET=your-billing-bucket-name
AWS_REGION=eu-west-1
ANTHROPIC_API_KEY=sk-ant-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
TIMESTREAM_DATABASE=cost-advisor
TIMESTREAM_TABLE=billing-costs
EOF

# 4. Run locally (requires AWS credentials in environment or ~/.aws)
python -c "from lambda_handler import handler; handler({}, None)"

# 5. Run tests
pip install pytest
pytest tests/ -v
```

---

## AWS deployment steps

```bash
# 1. Zip the Lambda package
zip -r lambda.zip lambda_handler.py src/ prompts/ requirements.txt

# 2. Create or update the Lambda function
aws lambda create-function \
  --function-name cost-optimization-advisor \
  --runtime python3.12 \
  --handler lambda_handler.handler \
  --zip-file fileb://lambda.zip \
  --role arn:aws:iam::ACCOUNT_ID:role/cost-advisor-role \
  --timeout 300 \
  --memory-size 512

# 3. Set environment variables
aws lambda update-function-configuration \
  --function-name cost-optimization-advisor \
  --environment "Variables={
    AWS_BILLING_BUCKET=your-bucket,
    AWS_REGION=eu-west-1,
    ANTHROPIC_API_KEY=sk-ant-...,
    SLACK_WEBHOOK_URL=https://hooks.slack.com/...,
    TIMESTREAM_DATABASE=cost-advisor,
    TIMESTREAM_TABLE=billing-costs
  }"

# 4. Create the IAM role using infra/iam_policy.json
#    (replace ${BILLING_BUCKET} with your actual bucket name)

# 5. Create EventBridge daily rule
aws events put-rule \
  --name cost-advisor-daily \
  --schedule-expression "cron(0 8 * * ? *)" \
  --state ENABLED

aws events put-targets \
  --rule cost-advisor-daily \
  --targets "Id=cost-advisor-lambda,Arn=arn:aws:lambda:REGION:ACCOUNT_ID:function:cost-optimization-advisor"
```

---

## How to configure anomaly thresholds

Edit `src/anomaly_detection.py` — the `_severity` function controls thresholds:

```python
def _severity(deviation_pct: float) -> str:
    if deviation_pct > 100:   # >100% above baseline → high
        return "high"
    elif deviation_pct > 50:  # 50–100% above baseline → medium
        return "medium"
    else:                     # 20–50% above baseline → low
        return "low"
```

The z-score threshold (2σ) is set in `_zscore_anomalies`. Lower it to catch smaller anomalies:

```python
threshold = mean + 2 * std  # change 2 to 1.5 for more sensitivity
```

The Isolation Forest contamination parameter (default 5%) can be adjusted:

```python
clf = IsolationForest(contamination=0.05, ...)  # increase for more anomalies
```

---

## Example Slack output

```
💰 Cost Anomaly Report — 2024-01-31
────────────────────────────────────
🔴 EC2 | eu-west-1 | Team: platform
• Actual: $500.00 vs baseline $10.00 (+4900.0%)
• EC2 costs spiked due to 12 untagged t3.large instances launched on Jan 30.
  Terminate idle instances in the EC2 console to save approximately $490/month.

🟡 S3 | eu-west-1 | Team: data
• Actual: $15.00 vs baseline $8.00 (+87.5%)
• S3 egress costs rose due to increased cross-region replication traffic.
  Switch to S3 Transfer Acceleration or review replication rules to save ~$7/month.

Total anomalies: 2 | High: 1 | Medium: 1 | Low: 0
```
