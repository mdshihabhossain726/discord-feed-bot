import json
import logging

from app.config.logging import JsonFormatter, redact_text, redact_value


def test_bearer_token_redacted():
    out = redact_text("Authorization failed for Bearer abcdef1234567890XYZ")
    assert "abcdef1234567890XYZ" not in out
    assert "Bearer" in out


def test_query_param_secret_redacted_but_key_kept():
    out = redact_text("GET /cb?code=1&access_token=supersecretvalue&x=2")
    assert "supersecretvalue" not in out
    assert "access_token=[REDACTED]" in out
    assert "x=2" in out


def test_discord_token_shape_redacted():
    token = "MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.GabcDE." + "a" * 30
    assert token not in redact_text(f"login with {token} failed")


def test_sensitive_dict_keys_redacted_recursively():
    out = redact_value({"user": "bob", "client_secret": "x", "nested": {"refresh_token": "y", "ok": 1}})
    assert out["user"] == "bob"
    assert out["client_secret"] == "[REDACTED]"
    assert out["nested"]["refresh_token"] == "[REDACTED]"
    assert out["nested"]["ok"] == 1


def test_formatter_emits_json_and_redacts_extra_and_exceptions():
    rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "msg %s", ("Bearer abcdefghijklmnop",), None)
    rec.access_token = "leak-me"
    rec.guild_id = 42
    try:
        raise RuntimeError("boom token=abc123secret")
    except RuntimeError:
        import sys
        rec.exc_info = sys.exc_info()
    data = json.loads(JsonFormatter().format(rec))
    assert data["level"] == "ERROR"
    assert data["guild_id"] == 42
    assert data["access_token"] == "[REDACTED]"
    assert "abcdefghijklmnop" not in data["message"]
    assert "abc123secret" not in data["exception"]
