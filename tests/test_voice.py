import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.brain.voice import VoiceProcessor, VoiceAnalysisResult
from src.notifier.telegram import TelegramNotifier
from src.collector.tg_collector import TelegramCollector


@pytest.mark.asyncio
async def test_voice_processor_empty_payload():
    """Verify VoiceProcessor handles empty payload gracefully."""
    vp = VoiceProcessor(groq_api_key="")
    res = await vp.process_voice(voice_bytes=b"")
    assert res.success is False
    assert res.error == "Empty voice payload"


@pytest.mark.asyncio
async def test_voice_processor_groq_success():
    """Verify Groq Cloud Whisper STT when API key is configured and request succeeds."""
    vp = VoiceProcessor(groq_api_key="gsk_valid_key_12345")
    assert vp.has_groq is True

    fake_response = MagicMock(spec=httpx.Response)
    fake_response.is_success = True
    fake_response.json.return_value = {"text": "Здравствуйте, перенесите пару на пятницу"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_response
        res = await vp.process_voice(
            voice_bytes=b"OGG_DUMMY_AUDIO_DATA",
            duration_seconds=10,
        )

        assert res.success is True
        assert res.transcription == "Здравствуйте, перенесите пару на пятницу"
        assert res.engine == "groq-whisper-large-v3-turbo"
        assert res.duration_seconds == 10
        mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_processor_groq_fallback_to_local():
    """Verify fallback to local faster-whisper when Groq API fails."""
    vp = VoiceProcessor(groq_api_key="gsk_valid_key_12345")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.HTTPError("Groq Down")):
        with patch.object(
            vp,
            "_transcribe_local",
            new_callable=AsyncMock,
            return_value=VoiceAnalysisResult(
                success=True,
                transcription="Локальное распознавание через faster-whisper",
                engine="faster-whisper-base",
                duration_seconds=5,
            ),
        ) as mock_local:
            res = await vp.process_voice(
                voice_bytes=b"OGG_DUMMY_AUDIO_DATA",
                duration_seconds=5,
            )

            assert res.success is True
            assert res.transcription == "Локальное распознавание через faster-whisper"
            assert res.engine == "faster-whisper-base"
            mock_local.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_processor_local_whisper_direct():
    """Verify direct local faster-whisper execution when Groq is not configured."""
    vp = VoiceProcessor(groq_api_key="")
    assert vp.has_groq is False

    mock_segment = MagicMock()
    mock_segment.text = "Тестовая транскрипция офлайн"
    mock_info = MagicMock()
    mock_info.language = "ru"
    mock_info.duration = 4.5

    mock_whisper_model = MagicMock()
    mock_whisper_model.transcribe.return_value = ([mock_segment], mock_info)

    with patch.object(vp, "_get_local_model", return_value=mock_whisper_model):
        res = await vp.process_voice(
            voice_bytes=b"OGG_DUMMY_AUDIO_DATA",
            duration_seconds=4,
        )

        assert res.success is True
        assert res.transcription == "Тестовая транскрипция офлайн"
        assert res.language == "ru"
        assert res.engine == f"faster-whisper-{vp.whisper_model_size}"


@pytest.mark.asyncio
async def test_voice_processor_gemini_success():
    """Verify Gemini Multimodal Audio STT when Groq is unavailable."""
    vp = VoiceProcessor(groq_api_key="", gemini_api_key="valid_gemini_key_123")
    assert vp.has_groq is False
    assert vp.has_gemini is True

    with patch.object(
        vp,
        "_transcribe_gemini",
        new_callable=AsyncMock,
        return_value=VoiceAnalysisResult(
            success=True,
            transcription="Расшифровка длинного аудио через Gemini Multimodal STT",
            engine="gemini-gemini-3.5-flash-lite",
            duration_seconds=873,
        ),
    ) as mock_gemini:
        res = await vp.process_voice(
            voice_bytes=b"LONG_AUDIO_PAYLOAD",
            mime_type="audio/mp3",
            duration_seconds=873,
        )

        assert res.success is True
        assert res.transcription == "Расшифровка длинного аудио через Gemini Multimodal STT"
        assert res.engine == "gemini-gemini-3.5-flash-lite"
        mock_gemini.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_processor_groq_failover_to_gemini():
    """Verify failover to Gemini when Groq fails."""
    vp = VoiceProcessor(groq_api_key="gsk_key", gemini_api_key="gemini_key")
    assert vp.has_groq is True
    assert vp.has_gemini is True

    with patch.object(vp, "_transcribe_groq", side_effect=RuntimeError("Groq 503 Overloaded")):
        with patch.object(
            vp,
            "_transcribe_gemini",
            new_callable=AsyncMock,
            return_value=VoiceAnalysisResult(
                success=True,
                transcription="Успешный фоллбек на Gemini",
                engine="gemini-gemini-3.5-flash-lite",
                duration_seconds=15,
            ),
        ) as mock_gemini:
            res = await vp.process_voice(
                voice_bytes=b"VOICE_DATA",
                duration_seconds=15,
            )
            assert res.success is True
            assert res.transcription == "Успешный фоллбек на Gemini"
            mock_gemini.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_notifier_voice_card():
    """Verify formatting of voice transcription card."""
    notifier = TelegramNotifier(bot_token=None, user_id=None)

    voice_res = VoiceAnalysisResult(
        success=True,
        transcription="Здравствуйте, перенесите, пожалуйста, консультацию на пятницу.",
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
