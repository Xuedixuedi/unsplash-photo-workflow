import os

from upw.redact import redact, redact_obj


def test_redacts_bearer_query_and_env(monkeypatch) -> None:
    monkeypatch.setenv("UNSPLASH_USER_TOKEN", "super-secret-token")
    monkeypatch.setenv("LLM_API_KEY", "sk-live-key")
    text = "Authorization: Bearer super-secret-token client_secret=sk-live-key&code=abc"
    cleaned = redact(text)
    assert "super-secret-token" not in cleaned
    assert "sk-live-key" not in cleaned
    assert "Bearer ***REDACTED***" in cleaned
    assert "client_secret=***REDACTED***" in cleaned
    assert "code=***REDACTED***" in cleaned
    assert os.environ["UNSPLASH_USER_TOKEN"] == "super-secret-token"


def test_redact_obj_walks_containers() -> None:
    cleaned = redact_obj({"token": "Bearer abc.def-ghi", "nested": ["ok"]})
    assert cleaned["token"] == "Bearer ***REDACTED***"
    assert cleaned["nested"] == ["ok"]
