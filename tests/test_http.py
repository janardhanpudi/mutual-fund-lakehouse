import pytest
import requests

from mf_lakehouse.common import http


class FakeResponse:
    def __init__(self, status):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


def fake_get(statuses, calls):
    def _get(*args, **kwargs):
        calls.append(1)
        return FakeResponse(statuses[len(calls) - 1])
    return _get


def test_404_is_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(http.requests, "get", fake_get([404, 200, 200], calls))
    with pytest.raises(requests.HTTPError):
        http.get("https://example.com", backoff=0)
    assert len(calls) == 1


def test_server_error_is_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(http.requests, "get", fake_get([503, 200], calls))
    assert http.get("https://example.com", backoff=0).status_code == 200
    assert len(calls) == 2
