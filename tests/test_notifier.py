import urllib.error

from stock_ai_research.notifier import send_feishu_webhook


class DummyResponse:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_send_webhook_success(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: DummyResponse(200))
    assert send_feishu_webhook({"a": 1}, "https://example.com", retries=1)


def test_send_webhook_fail(monkeypatch):
    def _raise(*args, **kwargs):
        raise urllib.error.URLError("failed")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    assert not send_feishu_webhook({"a": 1}, "https://example.com", retries=2)
