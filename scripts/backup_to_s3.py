"""
Disaster Recovery Pipeline: Encrypted Durable Off-Site Backup to Amazon S3
Requirement: INF-01 Disaster Recovery Hardening
Python / boto3 implementation mirroring scripts/backup_to_s3.sh
"""
from __future__ import annotations

import hashlib
import boto3


def run_s3_backup(
    dump_bytes: bytes,
    bucket_name: str,
    timestamp: str,
    kms_key_arn: str | None = None,
    retention_days: int = 30,
    region_name: str = "us-east-1",
    s3_client=None,
) -> dict:
    """Executes the S3 backup pipeline with KMS encryption, checksumming, and lifecycle policy."""
    if s3_client is None:
        s3_client = boto3.client("s3", region_name=region_name)

    # 1. Compute Cryptographic SHA-256 Checksum
    sha256_hash = hashlib.sha256(dump_bytes).hexdigest()

    # 2. Key paths
    prefix = f"postgres/automated/{timestamp}/"
    dump_key = f"{prefix}production_backup_{timestamp}.dump.enc"
    sha_key = f"{prefix}production_backup_{timestamp}.dump.enc.sha256"

    # 3. Upload encrypted dump to S3
    put_args = {
        "Bucket": bucket_name,
        "Key": dump_key,
        "Body": dump_bytes,
    }
    if kms_key_arn:
        put_args["ServerSideEncryption"] = "aws:kms"
        put_args["SSEKMSKeyId"] = kms_key_arn
    else:
        put_args["ServerSideEncryption"] = "AES256"

    s3_client.put_object(**put_args)

    # 4. Upload SHA-256 checksum file
    checksum_content = f"{sha256_hash}  production_backup_{timestamp}.dump.enc\n"
    s3_client.put_object(
        Bucket=bucket_name,
        Key=sha_key,
        Body=checksum_content.encode("utf-8"),
    )

    # 5. Apply 30-Day Lifecycle Retention Policy
    lifecycle_config = {
        "Rules": [
            {
                "ID": "DR-30-Day-Expiration-Policy",
                "Status": "Enabled",
                "Filter": {
                    "Prefix": "postgres/automated/"
                },
                "Expiration": {
                    "Days": retention_days
                },
                "NoncurrentVersionExpiration": {
                    "NoncurrentDays": 7
                }
            }
        ]
    }
    s3_client.put_bucket_lifecycle_configuration(
        Bucket=bucket_name,
        LifecycleConfiguration=lifecycle_config,
    )

    return {
        "status": "success",
        "bucket": bucket_name,
        "dump_key": dump_key,
        "sha_key": sha_key,
        "sha256": sha256_hash,
        "retention_days": retention_days,
        "kms_key_arn": kms_key_arn,
    }
