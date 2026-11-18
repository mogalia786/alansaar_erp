"""Dump the Render Postgres database and store the backup in Cloudflare R2.

Runs on a daily Render cron job but only creates a new dump when the most
recent backup is at least BACKUP_INTERVAL_DAYS old. This avoids the uneven
gaps caused by cron day-of-month expressions at month boundaries.
"""

import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError


REQUIRED_ENV = (
    "DATABASE_URL",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_S3_ENDPOINT_URL",
    "AWS_STORAGE_BUCKET_NAME",
)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def main() -> int:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
    if missing:
        print(f"ERROR: missing environment variables: {', '.join(missing)}")
        return 1

    prefix = os.environ.get("BACKUP_PREFIX", "db-backups").strip("/")
    interval_days = env_int("BACKUP_INTERVAL_DAYS", 15)
    retention_days = env_int("BACKUP_RETENTION_DAYS", 180)

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["AWS_S3_ENDPOINT_URL"],
        region_name="auto",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    bucket = os.environ["AWS_STORAGE_BUCKET_NAME"]
    full_prefix = f"{prefix}/" if prefix else ""

    response = s3.list_objects_v2(Bucket=bucket, Prefix=full_prefix)
    objects = response.get("Contents", [])
    now = datetime.now(timezone.utc)

    if objects:
        newest = max(obj["LastModified"] for obj in objects if obj.get("LastModified"))
        age = now - newest
        if age < timedelta(days=interval_days):
            print(
                f"Skipping backup: newest backup is {age.days} day(s) old "
                f"(interval: {interval_days} days)."
            )
            return 0

    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    filename = f"alansaar_erp_{timestamp}.dump"
    key = f"{full_prefix}{filename}"

    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        print("Creating database dump...")
        result = subprocess.run(
            [
                "pg_dump",
                "--dbname",
                os.environ["DATABASE_URL"],
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--schema=public",
                "--file",
                tmp_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("ERROR: pg_dump failed.")
            if result.stderr:
                print(result.stderr.strip())
            return 1

        size = os.path.getsize(tmp_path)
        if size == 0:
            print("ERROR: pg_dump produced an empty file.")
            return 1

        print(f"Uploading {size:,} bytes to s3://{bucket}/{key}")
        s3.upload_file(tmp_path, bucket, key)

        cutoff = now - timedelta(days=retention_days)
        deleted = 0
        for obj in objects:
            modified = obj.get("LastModified")
            if modified and modified < cutoff:
                s3.delete_object(Bucket=bucket, Key=obj["Key"])
                deleted += 1
        if deleted:
            print(f"Removed {deleted} backup(s) older than {retention_days} days.")

        print(f"Backup complete: {key}")
        return 0
    except ClientError as exc:
        print(f"ERROR: R2 upload failed: {exc}")
        return 1
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
