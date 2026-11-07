"""Copy landing files into the Databricks Volume, keeping the same layout, and verify each copy.

Databricks Free Edition cannot read our S3 bucket, so S3 is the archive and this Volume
is how files enter Databricks. Auto Loader picks them up from here.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from mf_lakehouse.common.config import get_env
from mf_lakehouse.common.s3 import LANDING_DIR, files_to_upload

logger = logging.getLogger(__name__)


def volume_root(catalog: str) -> str:
    return f"/Volumes/{catalog}/bronze/raw_landing"


def volume_path(path: Path, local_root: Path, root: str) -> str:
    """data/landing/ter/x/ter.parquet -> /Volumes/<catalog>/bronze/raw_landing/ter/x/ter.parquet"""
    return f"{root}/{path.relative_to(local_root).as_posix()}"


def upload_files(paths: list[Path], local_root: Path, root: str, files_api) -> list[str]:
    """Upload each file (overwriting), then check the Volume holds exactly as many bytes."""
    done = []
    for path in paths:
        target = volume_path(path, local_root, root)
        files_api.create_directory(target.rsplit("/", 1)[0])
        with path.open("rb") as f:
            files_api.upload(target, f, overwrite=True)
        remote_size = files_api.get_metadata(target).content_length
        local_size = path.stat().st_size
        if remote_size != local_size:
            raise RuntimeError(f"Volume check failed for {target}: local {local_size} bytes, Volume {remote_size} bytes")
        logger.info("copied %s (%d bytes)", target, local_size)
        done.append(target)
    return done


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Copy landing Parquet files into the Databricks Volume.")
    parser.add_argument("--source", help="only this source folder: nav, ter, aum or index_prices")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from databricks.sdk import WorkspaceClient

    root = volume_root(get_env("DATABRICKS_CATALOG"))
    paths = files_to_upload(LANDING_DIR, args.source)
    done = upload_files(paths, LANDING_DIR, root, WorkspaceClient().files)
    logger.info("done: %d files copied to %s and verified", len(done), root)


if __name__ == "__main__":
    main()