"""_make_client wires SDK-native retry/backoff onto both auth paths — no network.

Guards against silently dropping RETRY_OPTIONS, which is what keeps a transient
Vertex 429 from crashing the daily build (see editorial.RETRY_OPTIONS).
"""

import pytest

from still.pipeline import editorial


def _capture_client_kwargs(monkeypatch):
    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(editorial.genai, "Client", fake_client)
    return captured


def test_vertex_client_has_retry_options(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    captured = _capture_client_kwargs(monkeypatch)

    editorial._make_client()

    assert captured["vertexai"] is True
    assert captured["project"] == "test-project"
    retry = captured["http_options"].retry_options
    assert retry.attempts > 1
    assert 429 in retry.http_status_codes


def test_unconfigured_auth_raises_clear_error(monkeypatch):
    """No GEMINI_API_KEY and no GOOGLE_CLOUD_PROJECT → a RuntimeError that tells
    the user exactly which env vars to set, instead of an opaque SDK failure."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT|GEMINI_API_KEY"):
        editorial._make_client()


def test_developer_api_client_has_retry_options(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    captured = _capture_client_kwargs(monkeypatch)

    editorial._make_client()

    # Developer path: no vertex project pinned, but retry must still be applied.
    assert "vertexai" not in captured
    retry = captured["http_options"].retry_options
    assert retry.attempts > 1
    assert 429 in retry.http_status_codes
