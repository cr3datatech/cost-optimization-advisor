# Running the Cost Optimization Advisor

## Prerequisites

- Python 3.12+ and `pip install -r requirements.txt`
- AWS profile configured in `~/.aws/config`
- `.env` file (see `.env.example`)

## How to run locally

```bash
# 1. Create a .env file with your credentials (see .env.example)
AWS_PROFILE=your-aws-profile
AWS_BILLING_BUCKET=your-s3-bucket-name
AWS_REGION=eu-west-1
OPENAI_API_KEY=sk-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# 3. List profiles from ~/.aws/config
python scripts/manage.py list-profiles

# 4. Provision AWS infrastructure (S3 bucket + IAM role)
python scripts/manage.py infra

# 5. Analyse billing data from S3 (after CUR export arrives)
python scripts/manage.py analyze

# 6. Deploy Lambda
python scripts/manage.py deploy
python scripts/manage.py setup-schedule   # optional daily schedule
```

## Run tests (no credentials needed)

```bash
python3 -m pytest tests/ -v
```

---

## What's missing before it works end-to-end

### Required (it won't run without these)

1. **A real S3 bucket with billing CSVs** — AWS Cost & Usage Reports need to be enabled in your AWS Billing console and configured to export to an S3 bucket. This takes 24h to generate the first file.

2. **AWS credentials** — an IAM user/role with the permissions in `infra/iam_policy.json`. The `${BILLING_BUCKET}` placeholder in that file needs replacing with your actual bucket name.

3. **A Slack webhook URL** — create a Slack App at api.slack.com, add an Incoming Webhook, and copy the URL.

4. **An Anthropic API key** — from console.anthropic.com.

### Nice-to-have (not blocking, but gaps in the spec)

5. **Timestream integration is absent** — `TIMESTREAM_DATABASE` and `TIMESTREAM_TABLE` env vars are declared but never used. The spec mentions writing to Timestream for time-series storage but it wasn't implemented.

6. **No sample billing CSV in repo** — use `python scripts/manage.py analyze --local path/to/billing.csv` for offline testing.

---

## Quickest path to a working local test

Put a real billing CSV in an S3 bucket, fill in `.env`, then run:

```bash
python -c "from lambda_handler import handler; handler({}, None)"
```

To skip S3 entirely for a quick smoke test, a `--local` flag that reads a CSV from disk can be added.
