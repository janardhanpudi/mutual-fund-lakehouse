"""Upload landing files to S3, keeping the same folder layout, and verify each upload."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from mf_lakehouse.common.config import PROJECT_ROOT, get_env

logger = logging.getLogger(__name__)

LANDING_DIR = PROJECT_ROOT / "data" / "landing"
S3_PREFIX = "landing"


def s3_key(path: Path, local_root: Path, prefix: str = S3_PREFIX) -> str:
    """data/landing/nav/x/y.parquet -> landing/nav/x/y.parquet (always '/', even on Windows)."""
    return f"{prefix}/{path.relative_to(local_root).as_posix()}"


def files_to_upload(local_root: Path, source: str | None = None) -> list[Path]:
    """All Parquet files under the landing folder, or under one source (nav, ter, aum, index_prices)."""
    base = local_root / source if source else local_root
    if not base.exists():
        raise FileNotFoundError(f"Nothing to upload: {base} does not exist")
    return sorted(base.rglob("*.parquet"))


def upload_files(paths: list[Path], local_root: Path, bucket: str, client) -> list[str]:
    """Upload each file, then check S3 holds exactly as many bytes as the local file."""
    keys = []
    for path in paths:
        key = s3_key(path, local_root)
        client.upload_file(str(path), bucket, key)
        remote_size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
        local_size = path.stat().st_size
        if remote_size != local_size:
            raise RuntimeError(f"Upload check failed for {key}: local {local_size} bytes, S3 {remote_size} bytes")
        logger.info("uploaded s3://%s/%s (%d bytes)", bucket, key, local_size)
        keys.append(key)
    return keys


def make_client():
    import boto3

    return boto3.client("s3", region_name=get_env("AWS_REGION"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Upload landing Parquet files to S3.")
    parser.add_argument("--source", help="only this source folder: nav, ter, aum or index_prices")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    paths = files_to_upload(LANDING_DIR, args.source)
    keys = upload_files(paths, LANDING_DIR, get_env("S3_BUCKET_NAME"), make_client())
    logger.info("done: %d files uploaded and verified", len(keys))


if __name__ == "__main__":
    main()