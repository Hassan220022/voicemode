"""Tests for VOICEMODE_OMNIROUTE_ONLY fail-closed configuration.

Strict mode pins TTS/STT to exactly one non-OpenAI OpenAI-compatible endpoint
each, forces local auto-start/prefer flags off, and leaves default failover
behavior unchanged when the flag is unset.
"""

import os
from unittest.mock import patch

import pytest


OMNI_URL = "https://omniroute.example.com/v1"
OPENAI_URL = "https://api.openai.com/v1"
LOCAL_TTS = "http://127.0.0.1:8880/v1"
LOCAL_STT = "http://127.0.0.1:2022/v1"


@pytest.fixture
def isolated_reload(monkeypatch):
    """reload_configuration that ignores on-disk voicemode.env files."""
    import voice_mode.config as cfg

    monkeypatch.setattr(cfg, "load_voicemode_env", lambda: None)
    for key in (
        "VOICEMODE_OMNIROUTE_ONLY",
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


def test_valid_omniroute_only_single_non_openai_urls(isolated_reload, monkeypatch):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_OMNIROUTE_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", OMNI_URL)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", OMNI_URL)
    # Even if user left local/prefer flags on, strict mode forces them off.
    monkeypatch.setenv("VOICEMODE_PREFER_LOCAL", "true")
    monkeypatch.setenv("VOICEMODE_ALWAYS_TRY_LOCAL", "true")
    monkeypatch.setenv("VOICEMODE_AUTO_START_KOKORO", "true")
    monkeypatch.setenv("VOICEMODE_AUTO_START_SERVICES", "true")
    monkeypatch.setenv("VOICEMODE_SERVICE_AUTO_ENABLE", "true")

    cfg.reload_configuration()

    assert cfg.OMNIROUTE_ONLY is True
    assert cfg.TTS_BASE_URLS == [OMNI_URL]
    assert cfg.STT_BASE_URLS == [OMNI_URL]
    assert cfg.PREFER_LOCAL is False
    assert cfg.ALWAYS_TRY_LOCAL is False
    assert cfg.AUTO_START_KOKORO is False
    assert cfg.AUTO_START_SERVICES is False
    assert cfg.SERVICE_AUTO_ENABLE is False


@pytest.mark.parametrize(
    "tts,stt,missing",
    [
        (None, OMNI_URL, "VOICEMODE_TTS_BASE_URLS"),
        (OMNI_URL, None, "VOICEMODE_STT_BASE_URLS"),
        ("", OMNI_URL, "VOICEMODE_TTS_BASE_URLS"),
        (OMNI_URL, "", "VOICEMODE_STT_BASE_URLS"),
    ],
)
def test_rejects_missing_base_urls(isolated_reload, monkeypatch, tts, stt, missing):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_OMNIROUTE_ONLY", "true")
    if tts is not None:
        monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", tts)
    if stt is not None:
        monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", stt)

    with pytest.raises(cfg.OmniRouteConfigError) as exc:
        cfg.reload_configuration()
    assert missing in str(exc.value)
    assert "api.openai.com" not in str(exc.value).lower() or "forbids" in str(exc.value)


@pytest.mark.parametrize(
    "tts,stt",
    [
        (OPENAI_URL, OMNI_URL),
        (OMNI_URL, OPENAI_URL),
        (OPENAI_URL, OPENAI_URL),
    ],
)
def test_rejects_api_openai_com(isolated_reload, monkeypatch, tts, stt):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_OMNIROUTE_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", tts)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", stt)

    with pytest.raises(cfg.OmniRouteConfigError) as exc:
        cfg.reload_configuration()
    assert "api.openai.com" in str(exc.value)


def test_rejects_api_openai_com_trailing_dot(isolated_reload, monkeypatch):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_OMNIROUTE_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", "https://api.openai.com./v1")
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", OMNI_URL)
    with pytest.raises(cfg.OmniRouteConfigError) as exc:
        cfg.reload_configuration()
    assert "api.openai.com" in str(exc.value)


@pytest.mark.parametrize(
    "tts,stt",
    [
        (f"{OMNI_URL},{LOCAL_TTS}", OMNI_URL),
        (OMNI_URL, f"{OMNI_URL},{LOCAL_STT}"),
        (f"{OMNI_URL},{OPENAI_URL}", f"{OMNI_URL},{OPENAI_URL}"),
    ],
)
def test_rejects_comma_separated_failover_chains(isolated_reload, monkeypatch, tts, stt):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_OMNIROUTE_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", tts)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", stt)

    with pytest.raises(cfg.OmniRouteConfigError) as exc:
        cfg.reload_configuration()
    assert "failover" in str(exc.value).lower() or "exactly one" in str(exc.value).lower()


def test_default_failover_unchanged_when_flag_unset(isolated_reload, monkeypatch):
    cfg = isolated_reload
    assert "VOICEMODE_OMNIROUTE_ONLY" not in os.environ
    monkeypatch.delenv("VOICEMODE_TTS_BASE_URLS", raising=False)
    monkeypatch.delenv("VOICEMODE_STT_BASE_URLS", raising=False)

    cfg.reload_configuration()

    assert cfg.OMNIROUTE_ONLY is False
    assert OPENAI_URL in cfg.TTS_BASE_URLS
    assert LOCAL_TTS in cfg.TTS_BASE_URLS
    assert OPENAI_URL in cfg.STT_BASE_URLS
    assert LOCAL_STT in cfg.STT_BASE_URLS


def test_validate_helper_skips_when_disabled():
    from voice_mode.config import validate_omniroute_only_urls

    # Must not raise even with OpenAI + multi-URL when mode is off.
    validate_omniroute_only_urls(
        [LOCAL_TTS, OPENAI_URL],
        [LOCAL_STT, OPENAI_URL],
        enabled=False,
    )


def test_api_key_masked_in_config_display():
    from voice_mode.resources.configuration import mask_sensitive

    sample_key = "sk-omniroute-super-secret-key-value"
    masked = mask_sensitive(sample_key, "openai_api_key")
    assert sample_key not in masked
    assert "super-secret" not in masked
    assert masked.startswith("sk-omnir")
    assert masked.endswith("alue")
    assert "..." in masked


def test_omniroute_error_messages_never_include_api_key(isolated_reload, monkeypatch):
    cfg = isolated_reload
    monkeypatch.setenv("VOICEMODE_OMNIROUTE_ONLY", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-appear-in-errors")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", OPENAI_URL)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", OMNI_URL)

    with pytest.raises(cfg.OmniRouteConfigError) as exc:
        cfg.reload_configuration()
    assert "sk-should-never-appear-in-errors" not in str(exc.value)


@pytest.mark.asyncio
async def test_shared_startup_skips_kokoro_when_omniroute_only():
    """AUTO_START_KOKORO true is still blocked by OMNIROUTE_ONLY in shared startup."""
    import voice_mode.shared as shared

    with (
        patch("voice_mode.config.AUTO_START_KOKORO", True),
        patch("voice_mode.config.OMNIROUTE_ONLY", True),
        patch.object(shared, "_startup_initialized", False),
        patch("voice_mode.shared.subprocess.Popen") as popen,
    ):
        await shared.startup_initialization()
        popen.assert_not_called()


def test_clone_voice_does_not_bypass_omniroute_urls():
    from voice_mode.simple_failover import _resolve_tts_endpoints

    fake_profile = type(
        "P",
        (),
        {"base_url": "http://127.0.0.1:8890/v1", "model": "clone", "ref_text": None},
    )()

    with (
        patch("voice_mode.config.OMNIROUTE_ONLY", True),
        patch("voice_mode.voice_profiles.is_clone_voice", return_value=True),
        patch("voice_mode.voice_profiles.get_profile", return_value=fake_profile),
        patch("voice_mode.simple_failover.TTS_BASE_URLS", [OMNI_URL]),
    ):
        endpoints, profile = _resolve_tts_endpoints("my_clone", None)

    assert endpoints == [OMNI_URL]
    assert profile is fake_profile


def test_reload_updates_live_omniroute_flag(isolated_reload, monkeypatch):
    """Consumers that read vm_config.OMNIROUTE_ONLY see reload_configuration()."""
    import voice_mode.config as cfg
    import voice_mode.simple_failover as sf

    monkeypatch.setenv("VOICEMODE_OMNIROUTE_ONLY", "true")
    monkeypatch.setenv("VOICEMODE_TTS_BASE_URLS", OMNI_URL)
    monkeypatch.setenv("VOICEMODE_STT_BASE_URLS", OMNI_URL)
    cfg.reload_configuration()
    assert cfg.OMNIROUTE_ONLY is True
    assert sf.vm_config.OMNIROUTE_ONLY is True

    monkeypatch.setenv("VOICEMODE_OMNIROUTE_ONLY", "false")
    monkeypatch.delenv("VOICEMODE_TTS_BASE_URLS", raising=False)
    monkeypatch.delenv("VOICEMODE_STT_BASE_URLS", raising=False)
    cfg.reload_configuration()
    assert cfg.OMNIROUTE_ONLY is False
    assert sf.vm_config.OMNIROUTE_ONLY is False
