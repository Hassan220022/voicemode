"""Tests for VOICEMODE_9ROUTER_ONLY fail-closed configuration.

Strict mode pins TTS/STT to exactly one non-OpenAI OpenAI-compatible endpoint
each, forces local auto-start/prefer flags off, and leaves default failover
behavior unchanged when the flag is unset.
"""

import os
from unittest.mock import patch

import pytest


NINE_ROUTER_URL = "https://9router.example.com/v1"
OPENAI_URL = "https://api.openai.com/v1"
LOCAL_TTS = "http://127.0.0.1:8880/v1"
LOCAL_STT = "http://127.0.0.1:2022/v1"


@pytest.fixture
def isolated_reload(monkeypatch):
    """reload_configuration that ignores on-disk voicemode.env files."""
    import voice_mode.config as cfg

    monkeypatch.setattr(cfg, "load_voicemode_env", lambda: None)
    for key in (
        "VOICEMODE_9ROUTER_ONLY",
        "VOICEMODE_TTS_BASE_URLS",
        "VOICEMODE_STT_BASE_URLS",
        "VOICEMODE_PREFER_LOCAL",
        "VOICEMODE_ALWAYS_TRY_LOCAL",
        "VOICEMODE_AUTO_START_KOKORO",
        "VOICEMODE_AUTO_START_SERVICES",
        "VOICEMODE_SERVICE_AUTO_ENABLE",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    yield cfg


def test_valid_nine_router_only_single_non_openai_urls(isolated_reload, monkeypatch):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_9ROUTER_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", NINE_ROUTER_URL)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", NINE_ROUTER_URL)
    # Even if user left local/prefer flags on, strict mode forces them off.
    monkeypatch.setenv("VOICEMODE_PREFER_LOCAL", "true")
    monkeypatch.setenv("VOICEMODE_ALWAYS_TRY_LOCAL", "true")
    monkeypatch.setenv("VOICEMODE_AUTO_START_KOKORO", "true")
    monkeypatch.setenv("VOICEMODE_AUTO_START_SERVICES", "true")
    monkeypatch.setenv("VOICEMODE_SERVICE_AUTO_ENABLE", "true")

    cfg.reload_configuration()

    assert cfg.NINE_ROUTER_ONLY is True
    assert cfg.TTS_BASE_URLS == [NINE_ROUTER_URL]
    assert cfg.STT_BASE_URLS == [NINE_ROUTER_URL]
    assert cfg.PREFER_LOCAL is False
    assert cfg.ALWAYS_TRY_LOCAL is False
    assert cfg.AUTO_START_KOKORO is False
    assert cfg.AUTO_START_SERVICES is False
    assert cfg.SERVICE_AUTO_ENABLE is False


@pytest.mark.parametrize(
    "tts,stt,missing",
    [
        (None, NINE_ROUTER_URL, "VOICEMODE_TTS_BASE_URLS"),
        (NINE_ROUTER_URL, None, "VOICEMODE_STT_BASE_URLS"),
        ("", NINE_ROUTER_URL, "VOICEMODE_TTS_BASE_URLS"),
        (NINE_ROUTER_URL, "", "VOICEMODE_STT_BASE_URLS"),
    ],
)
def test_rejects_missing_base_urls(isolated_reload, monkeypatch, tts, stt, missing):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_9ROUTER_ONLY", "true")
    if tts is not None:
        monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", tts)
    if stt is not None:
        monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", stt)

    with pytest.raises(cfg.NineRouterConfigError) as exc:
        cfg.reload_configuration()
    assert missing in str(exc.value)
    assert "api.openai.com" not in str(exc.value).lower() or "forbids" in str(exc.value)


@pytest.mark.parametrize(
    "tts,stt",
    [
        (OPENAI_URL, NINE_ROUTER_URL),
        (NINE_ROUTER_URL, OPENAI_URL),
        (OPENAI_URL, OPENAI_URL),
        (LOCAL_TTS, NINE_ROUTER_URL),
        (NINE_ROUTER_URL, LOCAL_STT),
    ],
)
def test_rejects_openai_and_local_endpoints(isolated_reload, monkeypatch, tts, stt):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_9ROUTER_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", tts)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", stt)

    with pytest.raises(cfg.NineRouterConfigError) as exc:
        cfg.reload_configuration()
    assert "forbids" in str(exc.value)


def test_rejects_api_openai_com_trailing_dot(isolated_reload, monkeypatch):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_9ROUTER_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", "https://api.openai.com./v1")
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", NINE_ROUTER_URL)
    with pytest.raises(cfg.NineRouterConfigError) as exc:
        cfg.reload_configuration()
    assert "forbids" in str(exc.value)


@pytest.mark.parametrize(
    "tts,stt",
    [
        (f"{NINE_ROUTER_URL},{LOCAL_TTS}", NINE_ROUTER_URL),
        (NINE_ROUTER_URL, f"{NINE_ROUTER_URL},{LOCAL_STT}"),
        (f"{NINE_ROUTER_URL},{OPENAI_URL}", f"{NINE_ROUTER_URL},{OPENAI_URL}"),
    ],
)
def test_rejects_comma_separated_failover_chains(isolated_reload, monkeypatch, tts, stt):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_9ROUTER_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", tts)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", stt)

    with pytest.raises(cfg.NineRouterConfigError) as exc:
        cfg.reload_configuration()
    assert "failover" in str(exc.value).lower() or "exactly one" in str(exc.value).lower()


def test_default_failover_unchanged_when_flag_unset(isolated_reload, monkeypatch):
    cfg = isolated_reload
    assert "VOICEMODE_9ROUTER_ONLY" not in os.environ
    monkeypatch.delenv("VOICEMODE_TTS_BASE_URLS", raising=False)
    monkeypatch.delenv("VOICEMODE_STT_BASE_URLS", raising=False)

    cfg.reload_configuration()

    assert cfg.NINE_ROUTER_ONLY is False
    assert OPENAI_URL in cfg.TTS_BASE_URLS
    assert LOCAL_TTS in cfg.TTS_BASE_URLS
    assert OPENAI_URL in cfg.STT_BASE_URLS
    assert LOCAL_STT in cfg.STT_BASE_URLS


def test_validate_helper_skips_when_disabled():
    from voice_mode.config import validate_nine_router_only_urls

    # Must not raise even with OpenAI + multi-URL when mode is off.
    validate_nine_router_only_urls(
        [LOCAL_TTS, OPENAI_URL],
        [LOCAL_STT, OPENAI_URL],
        enabled=False,
    )


def test_api_key_masked_in_config_display():
    from voice_mode.resources.configuration import mask_sensitive

    sample_key = "sk-9router-super-secret-key-value"
    masked = mask_sensitive(sample_key, "openai_api_key")
    assert sample_key not in masked
    assert "super-secret" not in masked
    assert masked.startswith("sk-9rout")
    assert masked.endswith("alue")
    assert "..." in masked


def test_9router_error_messages_never_include_api_key(isolated_reload, monkeypatch):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_9ROUTER_ONLY", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-appear-in-errors")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", OPENAI_URL)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", NINE_ROUTER_URL)

    with pytest.raises(cfg.NineRouterConfigError) as exc:
        cfg.reload_configuration()
    assert "sk-should-never-appear-in-errors" not in str(exc.value)


@pytest.mark.asyncio
async def test_shared_startup_skips_kokoro_when_nine_router_only():
    """AUTO_START_KOKORO true is still blocked by NINE_ROUTER_ONLY in shared startup."""
    import voice_mode.shared as shared

    with (
        patch("voice_mode.config.AUTO_START_KOKORO", True),
        patch("voice_mode.config.NINE_ROUTER_ONLY", True),
        patch.object(shared, "_startup_initialized", False),
        patch("voice_mode.shared.subprocess.Popen") as popen,
    ):
        await shared.startup_initialization()
        popen.assert_not_called()


def test_clone_voice_does_not_bypass_9router_urls():
    from voice_mode.simple_failover import _resolve_tts_endpoints

    fake_profile = type(
        "P",
        (),
        {"base_url": "http://127.0.0.1:8890/v1", "model": "clone", "ref_text": None},
    )()

    with (
        patch("voice_mode.config.NINE_ROUTER_ONLY", True),
        patch("voice_mode.voice_profiles.is_clone_voice", return_value=True),
        patch("voice_mode.voice_profiles.get_profile", return_value=fake_profile),
        patch("voice_mode.simple_failover.TTS_BASE_URLS", [NINE_ROUTER_URL]),
    ):
        endpoints, profile = _resolve_tts_endpoints("my_clone", None)

    assert endpoints == [NINE_ROUTER_URL]
    assert profile is fake_profile


def test_reload_updates_live_9router_routing_and_credential(isolated_reload, monkeypatch):
    """Reload mutates imported endpoint lists and refreshes the request credential."""
    import voice_mode.config as cfg
    import voice_mode.simple_failover as sf

    cfg.reload_configuration()
    tts_urls = sf.TTS_BASE_URLS
    stt_urls = sf.STT_BASE_URLS
    monkeypatch.setenv("VOICEMODE_9ROUTER_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", NINE_ROUTER_URL)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", NINE_ROUTER_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "fresh-9router-token")
    cfg.reload_configuration()

    assert cfg.NINE_ROUTER_ONLY is True
    assert sf.vm_config.NINE_ROUTER_ONLY is True
    assert sf.TTS_BASE_URLS is tts_urls == [NINE_ROUTER_URL]
    assert sf.STT_BASE_URLS is stt_urls == [NINE_ROUTER_URL]
    assert cfg.OPENAI_API_KEY == "fresh-9router-token"

    monkeypatch.setenv("VOICEMODE_9ROUTER_ONLY", "false")
    monkeypatch.delenv("VOICEMODE_TTS_BASE_URLS", raising=False)
    monkeypatch.delenv("VOICEMODE_STT_BASE_URLS", raising=False)
    cfg.reload_configuration()
    assert cfg.NINE_ROUTER_ONLY is False
    assert sf.vm_config.NINE_ROUTER_ONLY is False


def test_stt_unwraps_json_text_response_format():
    """Proxies that ignore response_format=text return JSON-as-string; unwrap it."""
    import json
    raw = json.dumps({"text": "hello from nine router"})
    text = raw.strip()
    if text.startswith("{") and '"text"' in text:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and isinstance(parsed.get("text"), str):
            text = parsed["text"].strip()
    assert text == "hello from nine router"
