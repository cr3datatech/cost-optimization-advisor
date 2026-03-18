markdown
# CLAUDE.md — Cost Optimization AI Advisor

This file contains all instructions for building this project.
Read this fully before writing any code.

---

## What We're Building

A backend-only, Slack-first AI advisor that:
1. Ingests AWS billing data (Cost & Usage Reports from S3)
2. Detects cost anomalies using statistical analysis
3. Uses Claude (Anthropic API) to generate human-readable cost narratives and recommendations
4. Posts alerts and recommendations to Slack

**No GUI.** Output is via Slack messages and S3 JSON/CSV reports.

---

## Tech Stack

- **Language:** Python 3.12
- **Runtime:** AWS Lambda (triggered by EventBridge, daily)
- **Storage:** Amazon S3 (billing CSVs in, reports out) + Amazon Timestream (time-series cost data)
- **Anomaly Detection:** scikit-learn (Isolation Forest) + z-score (scipy)
- **LLM:** Anthropic Claude API (claude-3-5-sonnet)
- **Notifications:** Slack Incoming Webhooks
- **Infrastructure:** AWS (IAM, Lambda, EventBridge, S3, Timestream)

---

## Project Structure

Build the following file structure:

cost-optimization-advisor/
├── CLAUDE.md                   # This file
├── README.md                   # Setup and deployment guide
├── requirements.txt            # Python dependencies
├── lambda_handler.py           # Main Lambda entry point
├── src/
│   ├── __init__.py
│   ├── ingestion.py            # S3 billing CSV parsing & normalisation
│   ├── anomaly_detection.py    # Isolation Forest + z-score anomaly logic
│   ├── llm_advisor.py          # Claude API prompt builder & caller
│   └── slack_notifier.py       # Slack message formatter & webhook sender
├── prompts/
│   └── cost_narrative.txt      # Claude prompt template
├── tests/
│   ├── test_ingestion.py
│   ├── test_anomaly_detection.py
│   ├── test_llm_advisor.py
│   └── test_slack_notifier.py
└── infra/
    └── iam_policy.json         # Minimum IAM policy needed for Lambda execution
```

---

## Module Specifications

### lambda_handler.py
- Entry point: handler(event, context)
- Orchestrates the full pipeline:
  1. Call ingestion.load_latest_billing_data() → returns a normalised DataFrame
  2. Call anomaly_detection.detect_anomalies(df) → returns list of anomaly dicts
  3. For each anomaly, call llm_advisor.generate_recommendation(anomaly) → returns narrative string
  4. Call slack_notifier.post_summary(anomalies_with_narratives) → posts to Slack
- Read all config from environment variables (see Environment Variables section)

---

### src/ingestion.py

Function: load_latest_billing_data() -> pd.DataFrame

- Connect to S3 using boto3
- List objects in the billing bucket, find the most recent CSV file
- Download and parse the CSV into a pandas DataFrame
- Normalise columns to: date, service, region, account_id, team_tag, cost_usd
- Drop rows with null cost values
- Return the cleaned DataFrame

---

### src/anomaly_detection.py

Function: detect_anomalies(df: pd.DataFrame) -> list[dict]

- Group costs by service + region + team_tag
- For each group, calculate a 30-day rolling mean and standard deviation
- Flag any data point where cost > mean + 2σ as an anomaly (z-score method)
- Also run IsolationForest from scikit-learn across the full dataset for multi-dimensional outliers
- Return a list of anomaly dicts with keys:
  - service, region, account_id, team_tag
  - cost_usd (actual cost)
  - baseline_usd (30-day mean)
  - deviation_pct (% above baseline)
  - severity (low / medium / high based on deviation %)
  - date

Severity thresholds:
- low: 20–50% above baseline
- medium: 50–100% above baseline
- high: >100% above baseline

---

### src/llm_advisor.py

Function: `generate_recommendation(anomaly: dict)
[2:54 PM]-> str`

- Load the prompt template from prompts/cost_narrative.txt
- Inject the anomaly dict values into the template
- Call Anthropic Claude API (claude-3-5-sonnet-20241022)
- Return the text response (narrative + recommendation)

The narrative should include:
- What spiked, by how much, in which region/service
- Likely cause (inferred from context)
- Specific recommended action
- Estimated monthly saving if action is taken

---

### src/slack_notifier.py

Function: post_summary(anomalies: list[dict]) -> None

- Format a Slack Block Kit message
- Header: ":moneybag: Cost Anomaly Report — {date}"
- For each anomaly (sorted by severity desc):
  - Severity emoji: :red_circle: high / :large_yellow_circle: medium / :large_green_circle: low
  - Service, region, team tag
  - Actual vs baseline cost
  - Claude's recommendation narrative
- Footer: "Total anomalies: X | High: X | Medium: X | Low: X"
- POST to SLACK_WEBHOOK_URL environment variable using requests

---

### prompts/cost_narrative.txt

Write a prompt template with {placeholders} for:
- {service} — AWS service name
- {region} — AWS region
- {team_tag} — team tag value
- {cost_usd} — actual cost
- {baseline_usd} — 30-day baseline
- {deviation_pct} — % above baseline
- {date} — date of anomaly

The prompt should instruct Claude to:
- Write 2–3 sentences max
- Be specific and actionable
- Suggest a concrete remediation step
- Estimate savings where possible
- Avoid jargon and be direct

---

## Environment Variables

The Lambda function reads these from environment (set in AWS Lambda console or .env for local dev):

AWS_BILLING_BUCKET=your-billing-bucket-name
AWS_REGION=eu-west-1
ANTHROPIC_API_KEY=sk-ant-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
TIMESTREAM_DATABASE=cost-advisor
TIMESTREAM_TABLE=billing-costs




---

## requirements.txt

anthropic>=0.25.0
boto3>=1.34.0
pandas>=2.2.0
scikit-learn>=1.4.0
scipy>=1.13.0
requests>=2.31.0
python-dotenv>=1.0.0




---

## infra/iam_policy.json

Write a minimum-privilege IAM policy that allows Lambda to:
- s3:GetObject and s3:ListBucket on the billing bucket
- timestream:WriteRecords and timestream:DescribeEndpoints
- logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents (CloudWatch)

---

## Tests

Write unit tests for each module using pytest. Use unittest.mock to mock:
- boto3 S3 calls in test_ingestion.py
- anthropic.Anthropic client in test_llm_advisor.py
- requests.post in test_slack_notifier.py

Each test file should have at least:
- 1 happy path test
- 1 edge case (empty data, API error, etc.)

---

## README.md

Write a README with these sections:
1. **What it does** (2–3 sentences)
2. **Architecture diagram** (ASCII or described)
3. **Prerequisites** (AWS account, Anthropic API key, Slack webhook)
4. **Local development setup** (clone, pip install, .env setup, run locally)
5. **AWS deployment steps** (zip Lambda, set env vars, EventBridge rule)
6. **How to configure anomaly thresholds**
7. **Example Slack output** (mock screenshot description)

---

## Build Order

Build in this order to avoid dependency issues:

1. requirements.txt
2. src/ingestion.py + tests/test_ingestion.py
3. src/anomaly_detection.py + tests/test_anomaly_detection.py
4. prompts/cost_narrative.txt
5. src/llm_advisor.py + tests/test_llm_advisor.py
6. src/slack_notifier.py + tests/test_slack_notifier.py
7. lambda_handler.py
8. infra/iam_policy.json
9. README.md

---

## Done When

- [ ] All modules implemented
- [ ] All tests pass (pytest tests/)
- [ ] lambda_handler.py runs end-to-end locally with a sample CSV
- [ ] Slack message posts successfully with mock data
- [ ] README is complete
```