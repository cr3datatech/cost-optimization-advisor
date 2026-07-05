#!/usr/bin/env python3
"""Manage cost-optimization-advisor infrastructure, deployment, and analysis."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from botocore.exceptions import ClientError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DIST_DIR = ROOT / "dist"
PACKAGE_DIR = DIST_DIR / "package"
LAYER_DIR = DIST_DIR / "layer"
LAYER_PYTHON_DIR = LAYER_DIR / "python"
ZIP_PATH = DIST_DIR / "lambda.zip"
LAYER_ZIP_PATH = DIST_DIR / "layer.zip"
FULL_ZIP_PATH = DIST_DIR / "lambda-full.zip"
LAYER_REQUIREMENTS = ROOT / "requirements-lambda-layer.txt"
LAMBDA_DIRECT_UPLOAD_LIMIT = 50 * 1024 * 1024

LAMBDA_ENV_KEYS = (
    "AWS_BILLING_BUCKET",
    "OPENAI_API_KEY",
    "SLACK_WEBHOOK_URL",
)


def _import_boto3():
    import boto3

    return boto3


def load_config(profile_override: str | None = None) -> str:
    load_dotenv(ROOT / ".env")
    return resolve_profile(profile_override)


def resolve_profile(profile_override: str | None) -> str:
    profile = (profile_override or os.environ.get("AWS_PROFILE", "")).strip()
    if not profile:
        print(
            "Error: AWS_PROFILE is required.\n"
            "Add AWS_PROFILE=your-profile to .env (see .env.example), "
            "or pass --profile your-profile.",
            file=sys.stderr,
        )
        sys.exit(1)

    boto3 = _import_boto3()
    available = boto3.Session().available_profiles
    if profile not in available:
        print(
            f"Error: profile '{profile}' was not found in ~/.aws/config.\n"
            f"Available profiles: {', '.join(available) or '(none)'}",
            file=sys.stderr,
        )
        sys.exit(1)

    return profile


def get_session(profile: str):
    boto3 = _import_boto3()
    return boto3.Session(profile_name=profile)


def require_env(*keys: str) -> None:
    missing = [key for key in keys if not os.environ.get(key)]
    if missing:
        print(f"Error: missing required .env values: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def lambda_environment() -> dict[str, str]:
    require_env(*LAMBDA_ENV_KEYS)
    return {key: os.environ[key] for key in LAMBDA_ENV_KEYS}


def cmd_infra(args: argparse.Namespace) -> None:
    from src.infra import format_infra_summary, provision_infrastructure

    profile = load_config(args.profile)
    require_env("AWS_BILLING_BUCKET")
    region = os.environ.get("AWS_REGION", "eu-west-1")
    bucket_name = os.environ["AWS_BILLING_BUCKET"]
    role_name = os.environ.get("LAMBDA_ROLE_NAME", "cost-advisor-lambda-role").strip()

    print(f"Using AWS profile: {profile}")
    session = get_session(profile)
    result = provision_infrastructure(session, bucket_name, region, role_name)
    print(format_infra_summary(result, region))


def cmd_analyze(args: argparse.Namespace) -> None:
    from src.analyze import format_analysis_report, run_analysis, save_report

    load_config(args.profile)
    if not args.local:
        require_env("AWS_BILLING_BUCKET")

    if args.with_narratives:
        require_env("OPENAI_API_KEY")

    print(f"Using AWS profile: {os.environ.get('AWS_PROFILE')}")
    report, source = run_analysis(local_csv=args.local, with_narratives=args.with_narratives)
    print()
    print(format_analysis_report(report, source))

    if args.output:
        output_path = Path(args.output)
        save_report(report, output_path)
        print()
        print(f"Saved JSON report to {output_path}")


def clean_package_dir() -> None:
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)


def copy_source_files(target_dir: Path) -> None:
    shutil.copy(ROOT / "lambda_handler.py", target_dir / "lambda_handler.py")
    shutil.copytree(ROOT / "src", target_dir / "src")
    shutil.copytree(ROOT / "prompts", target_dir / "prompts")


def resolve_package_path(package_override: str | None = None) -> Path | None:
    configured = (package_override or os.environ.get("LAMBDA_PACKAGE_PATH", "")).strip()
    if not configured:
        return None

    path = Path(configured)
    if not path.is_file():
        print(f"Error: Lambda package not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path


def create_zip() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(PACKAGE_DIR))

    return ZIP_PATH


def lambda_runtime() -> str:
    return os.environ.get("LAMBDA_RUNTIME", "python3.12").strip() or "python3.12"


def prune_package_dir(target_dir: Path) -> None:
    for pattern in ("**/__pycache__", "**/*.pyc"):
        for path in target_dir.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)

    # Drop bulky test trees from large packages, but keep numpy internals intact.
    for package in ("pandas", "sklearn", "scipy", "openai"):
        tests_dir = target_dir / package / "tests"
        if tests_dir.exists():
            shutil.rmtree(tests_dir, ignore_errors=True)


def install_layer_dependencies(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    print("Installing layer dependencies for linux/amd64...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(LAYER_REQUIREMENTS),
            "-t",
            str(target_dir),
            "--platform",
            "manylinux2014_x86_64",
            "--python-version",
            "3.12",
            "--implementation",
            "cp",
            "--only-binary",
            ":all:",
            "--upgrade",
            "--quiet",
        ],
        check=True,
    )
    prune_package_dir(target_dir)


def zip_directory(source_dir: Path, zip_path: Path, arc_prefix: Path | None = None) -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                relative = path.relative_to(source_dir)
                archive_name = relative if arc_prefix is None else arc_prefix / relative
                archive.write(path, archive_name)

    return zip_path


def build_layer_package() -> Path:
    print("Building Lambda layer package...")
    if LAYER_DIR.exists():
        shutil.rmtree(LAYER_DIR)
    install_layer_dependencies(LAYER_PYTHON_DIR)
    zip_path = zip_directory(LAYER_PYTHON_DIR, LAYER_ZIP_PATH, arc_prefix=Path("python"))
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Created {zip_path} ({size_mb:.1f} MB)")
    return zip_path


def zip_code_payload(session, zip_path: Path, bucket_key: str) -> dict:
    zip_bytes = zip_path.read_bytes()
    if len(zip_bytes) <= LAMBDA_DIRECT_UPLOAD_LIMIT:
        return {"ZipFile": zip_bytes}

    bucket = os.environ["AWS_BILLING_BUCKET"]
    region = os.environ.get("AWS_REGION", "eu-west-1")
    s3 = session.client("s3", region_name=region)
    print(f"Uploading package to s3://{bucket}/{bucket_key}...")
    s3.upload_file(str(zip_path), bucket, bucket_key)
    return {"S3Bucket": bucket, "S3Key": bucket_key}


def publish_layer(session, function_name: str) -> str:
    layer_name = os.environ.get("LAMBDA_LAYER_NAME", "cost-advisor-deps").strip()
    zip_path = build_layer_package()
    content = zip_code_payload(
        session,
        zip_path,
        f"lambda/layers/{function_name}/layer.zip",
    )
    lambda_client = session.client("lambda", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    response = lambda_client.publish_layer_version(
        LayerName=layer_name,
        Description="Dependencies for cost-optimization-advisor",
        Content=content,
        CompatibleRuntimes=[lambda_runtime()],
    )
    layer_arn = response["LayerVersionArn"]
    print(f"Published layer: {layer_arn}")
    return layer_arn


def build_full_package() -> Path:
    """Build a Lambda zip with application source and Python dependencies."""
    print("Building full Lambda package...")
    clean_package_dir()
    copy_source_files(PACKAGE_DIR)
    print("Installing dependencies for linux/amd64...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(ROOT / "requirements.txt"),
            "-t",
            str(PACKAGE_DIR),
            "--platform",
            "manylinux2014_x86_64",
            "--python-version",
            "3.12",
            "--implementation",
            "cp",
            "--only-binary",
            ":all:",
            "--upgrade",
            "--quiet",
        ],
        check=True,
    )

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if FULL_ZIP_PATH.exists():
        FULL_ZIP_PATH.unlink()

    with zipfile.ZipFile(FULL_ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(PACKAGE_DIR))

    size_mb = FULL_ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"Created {FULL_ZIP_PATH} ({size_mb:.1f} MB)")
    return FULL_ZIP_PATH


def cmd_build_package(args: argparse.Namespace) -> None:
    if args.layer:
        build_layer_package()
    else:
        build_full_package()


def cmd_build_layer(_: argparse.Namespace) -> None:
    build_layer_package()


def cmd_invoke(args: argparse.Namespace) -> None:
    import json

    profile = load_config(args.profile)
    function_name = (
        args.function_name
        or os.environ.get("LAMBDA_FUNCTION_NAME", "").strip()
        or "cost-optimization-advisor"
    )
    region = os.environ.get("AWS_REGION", "eu-west-1")
    session = get_session(profile)
    lambda_client = session.client("lambda", region_name=region)

    print(f"Invoking {function_name} in {region}...")
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        LogType="Tail",
        Payload=json.dumps({}),
    )

    payload = response["Payload"].read().decode()
    print("Response:", payload)
    if response.get("FunctionError"):
        print("Function error:", response["FunctionError"], file=sys.stderr)
        sys.exit(1)

    if response.get("LogResult"):
        import base64

        print("\n--- Lambda logs ---")
        print(base64.b64decode(response["LogResult"]).decode()[-4000:])


def build_source_package() -> Path:
    print("Building Lambda source package...")
    clean_package_dir()
    copy_source_files(PACKAGE_DIR)
    zip_path = create_zip()
    size_kb = zip_path.stat().st_size / 1024
    print(f"Created {zip_path} ({size_kb:.1f} KB)")
    print(
        "Note: this zip contains application source only. "
        "Python dependencies must already be available in the Lambda runtime "
        "(layer or pre-built package via LAMBDA_PACKAGE_PATH)."
    )
    return zip_path


def build_package(package_override: str | None = None) -> Path:
    existing = resolve_package_path(package_override)
    if existing:
        print(f"Using Lambda package: {existing}")
        return existing
    return build_source_package()


def function_exists(lambda_client, function_name: str) -> bool:
    try:
        lambda_client.get_function(FunctionName=function_name)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def upload_lambda_package(session, function_name: str, zip_path: Path) -> dict:
    return zip_code_payload(
        session,
        zip_path,
        f"lambda/deployments/{function_name}/lambda.zip",
    )


def lambda_code_payload(session, function_name: str, zip_path: Path) -> dict:
    return upload_lambda_package(session, function_name, zip_path)


def deploy_lambda(profile: str, function_name: str, zip_path: Path, layer_arn: str | None = None) -> None:
    region = os.environ.get("AWS_REGION", "eu-west-1")
    session = get_session(profile)
    lambda_client = session.client("lambda", region_name=region)
    code = lambda_code_payload(session, function_name, zip_path)
    env_vars = {"Variables": lambda_environment()}
    config_kwargs = {
        "Environment": env_vars,
        "Timeout": 300,
        "MemorySize": 512,
        "Handler": "lambda_handler.handler",
        "Runtime": lambda_runtime(),
    }
    if layer_arn:
        config_kwargs["Layers"] = [layer_arn]

    if function_exists(lambda_client, function_name):
        print(f"Updating Lambda function '{function_name}' in {region}...")
        lambda_client.update_function_code(
            FunctionName=function_name,
            Publish=True,
            **code,
        )
        lambda_client.get_waiter("function_updated").wait(FunctionName=function_name)
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            **config_kwargs,
        )
    else:
        role_arn = os.environ.get("LAMBDA_ROLE_ARN", "").strip()
        if not role_arn:
            print(
                "Error: LAMBDA_ROLE_ARN is required for the first deploy.\n"
                "Run: python scripts/manage.py infra",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Creating Lambda function '{function_name}' in {region}...")
        lambda_client.create_function(
            FunctionName=function_name,
            Runtime=lambda_runtime(),
            Role=role_arn,
            Handler="lambda_handler.handler",
            Code=code,
            Timeout=300,
            MemorySize=512,
            Environment=env_vars,
            Layers=[layer_arn] if layer_arn else [],
            Publish=True,
        )

    print("Deploy complete.")


def setup_schedule(profile: str, function_name: str) -> None:
    region = os.environ.get("AWS_REGION", "eu-west-1")
    session = get_session(profile)
    lambda_client = session.client("lambda", region_name=region)

    if not function_exists(lambda_client, function_name):
        print(
            f"Error: Lambda function '{function_name}' was not found in {region}.\n"
            "Deploy the function first with: python scripts/manage.py deploy",
            file=sys.stderr,
        )
        sys.exit(1)

    sts = session.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    function_arn = f"arn:aws:lambda:{region}:{account_id}:function:{function_name}"
    rule_name = "cost-advisor-daily"
    rule_arn = f"arn:aws:events:{region}:{account_id}:rule/{rule_name}"

    events = session.client("events", region_name=region)

    print(f"Creating EventBridge rule '{rule_name}'...")
    events.put_rule(
        Name=rule_name,
        ScheduleExpression="cron(0 8 * * ? *)",
        State="ENABLED",
        Description="Daily cost optimization advisor run",
    )
    events.put_targets(
        Rule=rule_name,
        Targets=[{"Id": "cost-advisor-lambda", "Arn": function_arn}],
    )

    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId="eventbridge-daily",
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule_arn,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceConflictException":
            raise

    print("EventBridge schedule configured (daily at 08:00 UTC).")


def cmd_setup_schedule(args: argparse.Namespace) -> None:
    profile = load_config(args.profile)
    function_name = (
        args.function_name
        or os.environ.get("LAMBDA_FUNCTION_NAME", "").strip()
        or "cost-optimization-advisor"
    )

    print(f"Using AWS profile: {profile}")
    setup_schedule(profile, function_name)


def cmd_deploy(args: argparse.Namespace) -> None:
    profile = load_config(args.profile)
    function_name = (
        args.function_name
        or os.environ.get("LAMBDA_FUNCTION_NAME", "").strip()
        or "cost-optimization-advisor"
    )

    print(f"Using AWS profile: {profile}")
    session = get_session(profile)
    layer_arn = None
    if args.package:
        zip_path = build_package(args.package)
    else:
        layer_arn = publish_layer(session, function_name)
        zip_path = build_source_package()
    deploy_lambda(profile, function_name, zip_path, layer_arn=layer_arn)

    if args.setup_schedule:
        setup_schedule(profile, function_name)


def cmd_list_profiles(_: argparse.Namespace) -> None:
    boto3 = _import_boto3()
    profiles = boto3.Session().available_profiles
    if profiles:
        print("\n".join(profiles))
    else:
        print("No AWS profiles found.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage cost-optimization-advisor infrastructure, deployment, and analysis."
    )
    parser.add_argument(
        "--profile",
        help="AWS profile from ~/.aws/config (overrides AWS_PROFILE in .env)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    infra_parser = subparsers.add_parser(
        "infra",
        help="Create S3 billing bucket (if missing) and Lambda IAM role",
    )
    infra_parser.set_defaults(handler=cmd_infra)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Load billing data from S3 and analyse cost anomalies",
    )
    analyze_parser.add_argument(
        "--local",
        metavar="CSV",
        help="Analyse a local billing CSV instead of S3",
    )
    analyze_parser.add_argument(
        "--output",
        metavar="FILE",
        help="Save the analysis report as JSON",
    )
    analyze_parser.add_argument(
        "--with-narratives",
        action="store_true",
        help="Generate OpenAI recommendations for each anomaly",
    )
    analyze_parser.set_defaults(handler=cmd_analyze)

    build_parser_cmd = subparsers.add_parser(
        "build-package",
        help="Build a full Lambda zip with dependencies at dist/lambda-full.zip",
    )
    build_parser_cmd.add_argument(
        "--layer",
        action="store_true",
        help="Build a Lambda layer zip at dist/layer.zip instead",
    )
    build_parser_cmd.set_defaults(handler=cmd_build_package)

    build_layer_parser = subparsers.add_parser(
        "build-layer",
        help="Build a Lambda layer zip with dependencies at dist/layer.zip",
    )
    build_layer_parser.set_defaults(handler=cmd_build_layer)

    invoke_parser = subparsers.add_parser(
        "invoke",
        help="Invoke the deployed Lambda function",
    )
    invoke_parser.add_argument(
        "--function-name",
        help="Lambda function name (default: LAMBDA_FUNCTION_NAME or cost-optimization-advisor)",
    )
    invoke_parser.set_defaults(handler=cmd_invoke)

    deploy_parser = subparsers.add_parser(
        "deploy",
        help="Deploy the Lambda function (source zip or LAMBDA_PACKAGE_PATH)",
    )
    deploy_parser.add_argument(
        "--package",
        metavar="ZIP",
        help="Pre-built Lambda zip (overrides LAMBDA_PACKAGE_PATH in .env)",
    )
    deploy_parser.add_argument(
        "--function-name",
        help="Lambda function name (default: LAMBDA_FUNCTION_NAME or cost-optimization-advisor)",
    )
    deploy_parser.add_argument(
        "--setup-schedule",
        action="store_true",
        help="Create the daily EventBridge schedule after deploy",
    )
    deploy_parser.set_defaults(handler=cmd_deploy)

    schedule_parser = subparsers.add_parser(
        "setup-schedule",
        help="Create the daily EventBridge schedule (Lambda must already exist)",
    )
    schedule_parser.add_argument(
        "--function-name",
        help="Lambda function name (default: LAMBDA_FUNCTION_NAME or cost-optimization-advisor)",
    )
    schedule_parser.set_defaults(handler=cmd_setup_schedule)

    profiles_parser = subparsers.add_parser(
        "list-profiles",
        help="List profiles from ~/.aws/config",
    )
    profiles_parser.set_defaults(handler=cmd_list_profiles)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
