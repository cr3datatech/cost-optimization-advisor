# Running the Cost Optimization Advisor

## How to run locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create a .env file with your credentials
AWS_BILLING_BUCKET=your-s3-bucket-name
AWS_REGION=eu-west-1
ANTHROPIC_API_KEY=sk-ant-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# 3. Make sure your AWS credentials are configured
aws configure   # or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars

# 4. Run the Lambda handler directly
python -c "from lambda_handler import handler; handler({}, None)"
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

6. **No sample/mock CSV** — there's no test fixture file to do a full local dry-run without a real S3 bucket. You'd need to either point at a real bucket or add a `--local` mode that reads a local CSV.

7. **No Lambda deployment packaging** — no `Makefile` or script to zip the function with dependencies (Lambda needs a deployment package, not just source files).

8. **Dependencies aren't Lambda-compatible** — `scikit-learn`, `pandas`, and `scipy` are large and need to be bundled as a Lambda Layer or built for `linux/amd64`. They won't work if you just zip the source.

---

## Quickest path to a working local test

Put a real billing CSV in an S3 bucket, fill in `.env`, then run:

```bash
python -c "from lambda_handler import handler; handler({}, None)"
```

To skip S3 entirely for a quick smoke test, a `--local` flag that reads a CSV from disk can be added.
