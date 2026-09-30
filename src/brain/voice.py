import asyncio
import io
import logging
import os
import tempfile
from typing import Any
import httpx
from pydantic import BaseModel, Field

from src import config

logger = logging.getLogger(__name__)


class VoiceAnalysisResult(BaseModel):
    success: bool = True
    transcription: str = ""
    engine: str = "faster-whisper"
    language: str = "ru"
    duration_seconds: int | float | None = None
    error: str | None = None


class VoiceProcessor:
    """Dedicated Speech-to-Text (STT) engine decoupled from LLMs.
    
    Supports:
    1. Groq Cloud Whisper (whisper-large-v3-turbo) for ultra-fast cloud transcription when GROQ_API_KEY is available.
    2. Local faster-whisper (int8 on CPU) for fully autonomous, zero-cost, token-free offline transcription.
    """

    def __init__(
        self,
        groq_api_key: str | None = config.GROQ_API_KEY,
        gemini_api_key: str | None = config.GEMINI_API_KEY,
        gemini_model: str = config.GEMINI_MODEL,
        whisper_model_size: str = config.WHISPER_MODEL_SIZE,
        device: str = config.WHISPER_DEVICE,
        compute_type: str = config.WHISPER_COMPUTE_TYPE,
        cpu_threads: int = config.WHISPER_CPU_THREADS,
    ) -> None:
        self.groq_api_key = groq_api_key or ""
        self.gemini_api_key = gemini_api_key or ""
        self.gemini_model = gemini_model
        self.whisper_model_size = whisper_model_size
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self._local_model: Any = None
        self._model_lock = asyncio.Lock()

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key and not self.groq_api_key.startswith("gsk_Your"))

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key and not self.gemini_api_key.startswith("AIzaSyYour"))

    def _get_local_model(self) -> Any:
        if self._local_model is None:
            from faster_whisper import WhisperModel
            logger.info(
                "Initializing local faster-whisper model '%s' (device=%s, compute_type=%s, threads=%d)...",
                self.whisper_model_size,
                self.device,
                self.compute_type,
                self.cpu_threads,
            )
            self._local_model = WhisperModel(
                self.whisper_model_size,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
            )
            logger.info("Local faster-whisper model '%s' loaded successfully.", self.whisper_model_size)
        return self._local_model

    async def _transcribe_groq(
        self,
        voice_bytes: bytes,
        mime_type: str = "audio/ogg",
        duration_seconds: int | float | None = None,
    ) -> VoiceAnalysisResult:
        """Transcribe audio using Groq Cloud Whisper API (whisper-large-v3-turbo)."""
        ext = ".ogg" if "ogg" in mime_type else (".mp3" if "mp3" in mime_type else ".wav")
        files = {"file": (f"audio{ext}", voice_bytes, mime_type)}
        data = {
            "model": "whisper-large-v3-turbo",
            "language": "ru",
            "response_format": "json",
            "temperature": "0.0",
        }
        headers = {"Authorization": f"Bearer {self.groq_api_key}"}

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                data=data,
                files=files,
            )
            if response.is_success:
                res_data = response.json()
                text = (res_data.get("text") or "").strip()
                logger.info("Groq STT completed successfully in cloud: '%s'", text[:60])
                return VoiceAnalysisResult(
                    success=True,
                    transcription=text,
                    engine="groq-whisper-large-v3-turbo",
                    language="ru",
                    duration_seconds=duration_seconds,
                )
            else:
                logger.warning("Groq STT failed with status %d: %s", response.status_code, response.text)
                raise RuntimeError(f"Groq API error HTTP {response.status_code}: {response.text}")

    async def _transcribe_gemini(
        self,
        voice_bytes: bytes,
        mime_type: str = "audio/ogg",
        duration_seconds: int | float | None = None,
    ) -> VoiceAnalysisResult:
        """Transcribe audio using Gemini Multimodal Audio API."""
        from google import genai
        from google.genai import types

        resolved_mime = "audio/ogg"
        if "mp3" in mime_type or "mpeg" in mime_type:
            resolved_mime = "audio/mp3"
        elif "wav" in mime_type:
            resolved_mime = "audio/wav"

        client = genai.Client(api_key=self.gemini_api_key)
        prompt = (
            "You are a professional Russian speech transcriber. "
            "Listen carefully to this audio and transcribe it verbatim into Russian text. "
            "Output ONLY the exact transcribed text, without any additional explanations, headers, or commentary."
        )

        def _call_gemini():
            return client.models.generate_content(
                model=self.gemini_model,
                contents=[
                    types.Part.from_bytes(data=voice_bytes, mime_type=resolved_mime),
                    prompt,
                ],
            )

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, _call_gemini)
        text = (response.text or "").strip()
        logger.info("Gemini Multimodal STT completed successfully: '%s'", text[:60])
        return VoiceAnalysisResult(
            success=True,
            transcription=text,
            engine=f"gemini-{self.gemini_model}",
            language="ru",
            duration_seconds=duration_seconds,
        )

    def _transcribe_local_sync(
        self,
        voice_bytes: bytes,
        duration_seconds: int | float | None = None,
    ) -> VoiceAnalysisResult:
        """Synchronous local faster-whisper inference executed in worker thread."""
        model = self._get_local_model()
        
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
            tmp_file.write(voice_bytes)
            tmp_path = tmp_file.name

        try:
            segments, info = model.transcribe(
                tmp_path,
                language="ru",
                beam_size=5,
                vad_filter=True,
            )
            transcription_parts = [segment.text.strip() for segment in segments if segment.text.strip()]
            full_text = " ".join(transcription_parts).strip()
            
            logger.info("Local faster-whisper completed transcription: '%s'", full_text[:60])
            return VoiceAnalysisResult(
                success=True,
                transcription=full_text,
                engine=f"faster-whisper-{self.whisper_model_size}",
                language=info.language if hasattr(info, "language") else "ru",
                duration_seconds=duration_seconds or getattr(info, "duration", None),
            )
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    async def _transcribe_local(
        self,
        voice_bytes: bytes,
        duration_seconds: int | float | None = None,
    ) -> VoiceAnalysisResult:
        """Run local faster-whisper asynchronously without blocking the event loop."""
        async with self._model_lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                self._transcribe_local_sync,
                voice_bytes,
                duration_seconds,
            )

    async def process_voice(
        self,
        voice_bytes: bytes,
        mime_type: str = "audio/ogg",
        duration_seconds: int | float | None = None,
        sender_name: str | None = None,
        chat_title: str | None = None,
    ) -> VoiceAnalysisResult:
        """Transcribe voice note with Groq / Gemini cloud tier and instant local faster-whisper fallback."""
        if not voice_bytes:
            return VoiceAnalysisResult(success=False, error="Empty voice payload")

        # 1. Try Groq Cloud Whisper if configured
        if self.has_groq:
            try:
                logger.info("Attempting cloud transcription via Groq Whisper...")
                return await self._transcribe_groq(voice_bytes, mime_type, duration_seconds)
            except Exception as e:
                logger.warning("Groq Cloud Whisper failed (%s), trying next cloud engine.", e)

        # 2. Try Gemini Multimodal Audio if configured
        if self.has_gemini:
            try:
                logger.info("Attempting cloud transcription via Gemini Multimodal Audio...")
                return await self._transcribe_gemini(voice_bytes, mime_type, duration_seconds)
            except Exception as e:
                logger.warning("Gemini Multimodal Audio failed (%s), falling back to local faster-whisper.", e)

        # 3. Local faster-whisper fallback (zero-token, autonomous)
        try:
            logger.info("Running local faster-whisper STT...")
            return await self._transcribe_local(voice_bytes, duration_seconds)
        except Exception as e:
            logger.exception("Local faster-whisper transcription failed: %s", e)
            return VoiceAnalysisResult(
                success=False,
                error=f"Ошибка распознавания речи (STT): {e}",
                duration_seconds=duration_seconds,
            )
