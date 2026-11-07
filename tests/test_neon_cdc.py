import json
from datetime import datetime, timedelta, timezone

import pandas as pd
from botocore.exceptions import ClientError

from mf_lakehouse.extract.neon_cdc import (
    STATE_KEY, changes_sql, new_watermark, read_watermark, write_parquet, write_watermark,
)

T = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        body = self.objects[Key]
        return {"Body": type("B", (), {"read": lambda self: body})()}


def test_first_run_has_no_watermark_and_reads_everything():
    assert read_watermark(FakeS3(), "bucket") is None
    sql, params = changes_sql(None)
    assert "WHERE" not in sql and params == ()


def test_watermark_round_trips_through_s3():
    s3 = FakeS3()
    write_watermark(s3, "bucket", (T, "135762"))
    assert read_watermark(s3, "bucket") == (T, "135762")
    assert json.loads(s3.objects[STATE_KEY])["scheme_code"] == "135762"


def test_next_run_reads_after_the_last_position():
    sql, params = changes_sql((T, "135762"))
    assert "(updated_at, scheme_code) > (%s, %s)" in sql
    assert sql.endswith("ORDER BY updated_at, scheme_code")
    assert params == (T, "135762")


def test_watermark_is_last_row_read():
    changes = pd.DataFrame({
        "scheme_code": ["900001", "900002"],
        "updated_at": pd.to_datetime([T, T], utc=True),   # same timestamp: code breaks the tie
    })
    assert new_watermark(changes, None) == (T, "900002")


def test_watermark_stays_when_nothing_changed():
    empty = pd.DataFrame({"scheme_code": [], "updated_at": []})
    assert new_watermark(empty, (T, "1")) == (T, "1")


def test_each_run_gets_its_own_file(tmp_path):
    df = pd.DataFrame({"scheme_code": ["1"], "updated_at": pd.to_datetime([T], utc=True)})
    a = write_parquet(df, tmp_path, T)
    b = write_parquet(df, tmp_path, T + timedelta(hours=2))
    assert a != b and a.parent == b.parent
