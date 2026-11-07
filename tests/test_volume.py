from pathlib import Path
from types import SimpleNamespace

import pytest

from mf_lakehouse.common.s3 import files_to_upload
from mf_lakehouse.common.volume import upload_files, volume_path, volume_root

ROOT = volume_root("mf_lakehouse")


def make_landing(tmp_path: Path) -> Path:
    root = tmp_path / "landing"
    f = root / "ter/ter_month=2026-10/ter.parquet"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x" * 10)
    return root


class FakeFiles:
    """Stands in for WorkspaceClient().files."""

    def __init__(self, lose_bytes=0):
        self.dirs, self.files, self.lose_bytes = set(), {}, lose_bytes

    def create_directory(self, path):
        self.dirs.add(path)

    def upload(self, path, contents, overwrite=False):
        self.files[path] = len(contents.read()) - self.lose_bytes

    def get_metadata(self, path):
        return SimpleNamespace(content_length=self.files[path])


def test_path_mirrors_local_layout(tmp_path):
    root = make_landing(tmp_path)
    path = root / "ter/ter_month=2026-10/ter.parquet"
    assert volume_path(path, root, ROOT) == "/Volumes/mf_lakehouse/bronze/raw_landing/ter/ter_month=2026-10/ter.parquet"


def test_copy_creates_folder_and_is_verified(tmp_path):
    root = make_landing(tmp_path)
    fake = FakeFiles()
    done = upload_files(files_to_upload(root), root, ROOT, fake)
    assert done == [f"{ROOT}/ter/ter_month=2026-10/ter.parquet"]
    assert f"{ROOT}/ter/ter_month=2026-10" in fake.dirs


def test_size_mismatch_raises(tmp_path):
    root = make_landing(tmp_path)
    with pytest.raises(RuntimeError, match="Volume check failed"):
        upload_files(files_to_upload(root), root, ROOT, FakeFiles(lose_bytes=1))