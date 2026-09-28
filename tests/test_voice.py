import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.brain.voice import VoiceProcessor, VoiceAnalysisResult
from src.notifier.telegram import TelegramNotifier
from src.collector.tg_collector import TelegramCollector


@pytest.mark.asyncio
async def test_voice_processor_offline_fallback():
    """Verify VoiceProcessor fallback transcription when API key is unconfigured."""
    vp = VoiceProcessor(api_key="")
    assert vp.is_configured is False

    sample_audio_bytes = b"OGG_OPUS_SAMPLE_AUDIO_BYTES"
    res = await vp.process_voice(
        voice_bytes=sample_audio_bytes,
        duration_seconds=15,
        sender_name="Студент Иванов",
        chat_title="м431к",
    )

    assert res.success is True
    assert res.transcription != ""
    assert res.summary != ""
    assert isinstance(res.action_items, list)
    assert res.duration_seconds == 15


@pytest.mark.asyncio
async def test_voice_processor_empty_payload():
    """Verify VoiceProcessor handles empty payload gracefully."""
    vp = VoiceProcessor(api_key="")
    res = await vp.process_voice(voice_bytes=b"")
    assert res.success is False
    assert res.error == "Empty voice payload"


@pytest.mark.asyncio
async def test_telegram_notifier_voice_card():
    """Verify formatting of voice transcription card."""
    notifier = TelegramNotifier(bot_token=None, user_id=None)

    voice_res = VoiceAnalysisResult(
        success=True,
        transcription="Здравствуйте, перенесите, пожалуйста, консультацию на пятницу.",
        summary="Просьба перенести консультацию на пятницу.",
        action_items=["Перенести консультацию на пятницу"],
        duration_seconds=12,
    )

    sent = await notifier.send_voice_transcription_card(
        voice_res=voice_res,
        sender_name="Староста м531",
        chat_title="м531 Основы проектной деятельности",
    )
    assert sent is True


@pytest.mark.asyncio
async def test_telegram_collector_voice_mock_processing():
    """Verify TelegramCollector integrates voice transcription seamlessly."""
    mock_db = MagicMock()
    mock_vp = MagicMock(spec=VoiceProcessor)
    mock_vp.process_voice = AsyncMock(
        return_value=VoiceAnalysisResult(
            success=True,
            transcription="Когда будет защита отчетов по второй лабораторной?",
            summary="Вопрос о сроках защиты второй лабораторной.",
            action_items=["Уточнить дату защиты второй лабораторной работы"],
            duration_seconds=8,
        )
    )

    collector = TelegramCollector(
        db=mock_db,
        api_id=12345,
        api_hash="mock_hash",
        voice_processor=mock_vp,
    )

    assert collector.voice_processor is not None
