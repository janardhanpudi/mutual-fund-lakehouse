from pathlib import Path

import pytest

from mf_lakehouse.common.s3 import files_to_upload, s3_key, upload_files


def make_landing(tmp_path: Path) -> Path:
    root = tmp_path / "landing"
    for rel in ["nav/source=daily/run_date=2026-11-07/nav.parquet", "ter/ter_month=2026-10/ter.parquet"]:
        f = root / rel
        f.parent.mkdir(parents=True)
        f.write_bytes(b"x" * 10)
    return root


class FakeS3:
    """Stands in for boto3's S3 client; can pretend an upload was cut short."""

    def __init__(self, lose_bytes=0):
        self.objects, self.lose_bytes = {}, lose_bytes

    def upload_file(self, filename, bucket, key):
        self.objects[key] = Path(filename).stat().st_size - self.lose_bytes

    def head_object(self, Bucket, Key):
        return {"ContentLength": self.objects[Key]}


def test_key_mirrors_local_layout(tmp_path):
    root = make_landing(tmp_path)
    path = root / "nav/source=daily/run_date=2026-11-07/nav.parquet"
    assert s3_key(path, root) == "landing/nav/source=daily/run_date=2026-11-07/nav.parquet"


def test_files_can_be_limited_to_one_source(tmp_path):
    root = make_landing(tmp_path)
    assert len(files_to_upload(root)) == 2
    assert [p.name for p in files_to_upload(root, "ter")] == ["ter.parquet"]


def test_upload_is_verified(tmp_path):
    root = make_landing(tmp_path)
    s3 = FakeS3()
    keys = upload_files(files_to_upload(root), root, "bucket", s3)
    assert sorted(keys) == sorted(s3.objects)


def test_size_mismatch_raises(tmp_path):
    root = make_landing(tmp_path)
    with pytest.raises(RuntimeError, match="Upload check failed"):
        upload_files(files_to_upload(root), root, "bucket", FakeS3(lose_bytes=1))


def test_missing_source_folder_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="Nothing to upload"):
        files_to_upload(make_landing(tmp_path), "aum")