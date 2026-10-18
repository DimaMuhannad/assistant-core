"""Подключение к IMAP: широкий таймаут и одна повторная попытка (сбои сервера университета, ~10% циклов)."""
from __future__ import annotations

import pytest

from src.collector import email_collector as ec


class _FakeClient:
    instances: list["_FakeClient"] = []
    fail_connects = 0

    def __init__(self, host, port=993, ssl=True, timeout=None):
        type(self).instances.append(self)
        self.timeout = timeout
        self.logged_in = False
        self.shut = False
        if len(type(self).instances) <= type(self).fail_connects:
            raise TimeoutError("timed out")

    def login(self, user, password):
        self.logged_in = True

    def shutdown(self):
        self.shut = True


@pytest.fixture(autouse=True)
def _fake(monkeypatch):
    _FakeClient.instances = []
    _FakeClient.fail_connects = 0
    monkeypatch.setattr(ec, "IMAPClient", _FakeClient)


def test_open_imap_client_uses_wide_timeout():
    client = ec.open_imap_client("h", 993, "u", "p")

    assert client.timeout == ec.IMAP_TIMEOUT_SEC >= 45
    assert client.logged_in


def test_open_imap_client_retries_once_after_timeout():
    _FakeClient.fail_connects = 1

    client = ec.open_imap_client("h", 993, "u", "p")

    assert len(_FakeClient.instances) == 2
    assert client.logged_in


def test_open_imap_client_gives_up_after_second_timeout():
    _FakeClient.fail_connects = 2

    with pytest.raises(TimeoutError):
        ec.open_imap_client("h", 993, "u", "p")

    assert len(_FakeClient.instances) == 2
