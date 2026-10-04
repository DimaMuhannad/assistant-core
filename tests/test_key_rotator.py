import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src import config
from src.brain.key_rotator import GeminiKeyRotator, get_key_rotator, _current_rotator, key_rotator
from src.persona.current import current_persona, use_persona


@pytest.fixture
def mock_keys():
    return [
        "AQ.KeyOne11111111111111111111111111111111",
        "AQ.KeyTwo22222222222222222222222222222222",
        "AQ.KeyThree333333333333333333333333333333",
    ]


@pytest.fixture
def temp_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=AQ.KeyOne11111111111111111111111111111111\nGEMINI_MODEL=gemini-3.5-flash-lite\n")
    return env_file


def test_key_rotator_initialization(mock_keys, temp_env_file):
    rotator = GeminiKeyRotator(keys=mock_keys, env_path=temp_env_file)
    assert rotator.total_keys == 3
    assert rotator.get_active_key() == mock_keys[0]


def test_key_rotator_mark_exhausted(mock_keys, temp_env_file):
    rotator = GeminiKeyRotator(keys=mock_keys, env_path=temp_env_file)
    assert rotator.get_active_key() == mock_keys[0]

    # Exhaust Key 1
    next_key = rotator.mark_exhausted(mock_keys[0], retry_delay=10.0)
    assert next_key == mock_keys[1]
    assert rotator.get_active_key() == mock_keys[1]

    # Verify .env was synced
    env_content = temp_env_file.read_text()
    assert f"GEMINI_API_KEY={mock_keys[1]}" in env_content

    # Exhaust Key 2
    next_key_2 = rotator.mark_exhausted(mock_keys[1], retry_delay=10.0)
    assert next_key_2 == mock_keys[2]
    assert rotator.get_active_key() == mock_keys[2]


def test_key_rotator_cooldown_recovery(mock_keys, temp_env_file):
    rotator = GeminiKeyRotator(keys=mock_keys, env_path=temp_env_file)
    
    # Put Key 0 on a tiny cooldown of 0.05s
    rotator.mark_exhausted(mock_keys[0], retry_delay=0.05)
    assert rotator.get_active_key() == mock_keys[1]

    # Wait for cooldown to expire
    time.sleep(0.08)
    # Put Key 1 on long cooldown
    rotator.mark_exhausted(mock_keys[1], retry_delay=20.0)

    # Key 0 should be healthy again
    assert rotator.get_active_key() == mock_keys[0]


@pytest.mark.asyncio
async def test_execute_with_failover_success(mock_keys, temp_env_file):
    rotator = GeminiKeyRotator(keys=mock_keys, env_path=temp_env_file)

    async def mock_call(client):
        return "success_result"

    res = await rotator.execute_with_failover(mock_call)
    assert res == "success_result"


@pytest.mark.asyncio
async def test_execute_with_failover_rotates_on_429(mock_keys, temp_env_file):
    rotator = GeminiKeyRotator(keys=mock_keys, env_path=temp_env_file)

    calls = []

    async def mock_call(client):
        active_k = rotator.get_active_key()
        calls.append(active_k)
        if len(calls) == 1:
            raise Exception("429 RESOURCE_EXHAUSTED: Please retry in 15.0s")
        return f"recovered_with_{active_k}"

    res = await rotator.execute_with_failover(mock_call)
    assert res.startswith(f"recovered_with_{mock_keys[1]}")
    assert len(calls) == 2
    assert calls[0] == mock_keys[0]
    assert calls[1] == mock_keys[1]


@pytest.mark.asyncio
async def test_execute_with_failover_all_exhausted(mock_keys, temp_env_file):
    rotator = GeminiKeyRotator(keys=mock_keys, env_path=temp_env_file)

    async def mock_call(client):
        raise Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")

    with pytest.raises(Exception) as exc_info:
        await rotator.execute_with_failover(mock_call, max_attempts=3)
    assert "429" in str(exc_info.value)


def test_key_rotator_no_global_config_mutation(mock_keys, temp_env_file):
    orig_key = config.GEMINI_API_KEY
    rotator = GeminiKeyRotator(keys=mock_keys, env_path=temp_env_file)
    assert rotator.get_active_key() == mock_keys[0]

    # Exhaust Key 0
    next_key = rotator.mark_exhausted(mock_keys[0], retry_delay=10.0)
    assert next_key == mock_keys[1]

    # Verify global config was NOT mutated (D-02, ISO-01)
    assert config.GEMINI_API_KEY == orig_key

    # Verify temp_env_file WAS updated because env_path was explicitly provided
    env_content = temp_env_file.read_text()
    assert f"GEMINI_API_KEY={mock_keys[1]}" in env_content


def test_key_rotator_default_env_path_is_none(mock_keys):
    rotator = GeminiKeyRotator(keys=mock_keys)
    assert rotator.env_path is None

    # Rotator marks exhausted without error and without disk write
    next_key = rotator.mark_exhausted(mock_keys[0], retry_delay=10.0)
    assert next_key == mock_keys[1]
    assert rotator.sync_active_key_to_env(next_key) is False


def test_key_rotator_persona_isolation(mock_keys):
    # 1. Test ContextVar override
    custom_rotator = GeminiKeyRotator(keys=["custom_1", "custom_2"])
    token = _current_rotator.set(custom_rotator)
    try:
        assert get_key_rotator() is custom_rotator
        assert key_rotator.get_active_key() == "custom_1"
    finally:
        _current_rotator.reset(token)

    # 2. Test multi-persona isolation via use_persona
    base = current_persona()
    p1 = base.model_copy(update={"id": "tenant-p1", "gemini_keys": ["k-p1-alpha", "k-p1-beta"]})
    p2 = base.model_copy(update={"id": "tenant-p2", "gemini_keys": ["k-p2-gamma", "k-p2-delta"]})

    with use_persona(p1):
        rot1 = get_key_rotator()
        assert rot1.get_active_key() == "k-p1-alpha"
        rot1.mark_exhausted("k-p1-alpha", retry_delay=100.0)
        assert rot1.get_active_key() == "k-p1-beta"

    with use_persona(p2):
        rot2 = get_key_rotator()
        assert rot2 is not rot1
        assert rot2.get_active_key() == "k-p2-gamma"
        assert rot2.total_keys == 2

    with use_persona(p1):
        rot1_again = get_key_rotator()
        assert rot1_again is rot1
        # Cooldown is preserved for tenant-p1 without affecting tenant-p2
        assert rot1_again.get_active_key() == "k-p1-beta"

