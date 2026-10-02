"""Характеризация системных промптов (PER-07, BCK-01, D-07).

Эталоны в tests/fixtures/prompts_snapshot/ сняты с неизменённого кода (до переноса в Jinja2).
Тест снимает текст ПО МЕСТУ ВЫЗОВА LLM (подменённый клиент запоминает system_instruction
или contents) и сравнивает его с эталоном побайтно (UTF-8, без нормализации).

Тест не импортирует модульные константы промптов: они исчезнут при переносе в шаблоны,
а этот тест должен остаться без правок.
"""

import hashlib
import json
import subprocess
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest
from google import genai

from src.models.schedule import Lesson, LessonType
from src.storage.db import Database

REPO = Path(__file__).resolve().parents[1]
SNAP_DIR = Path(__file__).parent / "fixtures" / "prompts_snapshot"
MANIFEST = json.loads((SNAP_DIR / "MANIFEST.json").read_text(encoding="utf-8"))


def snapshot_bytes(key: str) -> bytes:
    """Побайтовое содержимое эталона по ключу манифеста."""
    return (SNAP_DIR / MANIFEST["prompts"][key]["file"]).read_bytes()


def prompt_inputs(key: str) -> dict[str, Any]:
    """Входные данные вызова, записанные в манифесте при снятии эталона."""
    return MANIFEST["prompts"][key]["inputs"]


class FakeGeminiClient:
    """Фейк клиента Gemini: запоминает model/contents/config каждого вызова, сети нет."""

    def __init__(self, text: str = "ok") -> None:
        self.calls: list[dict[str, Any]] = []
        outer = self

        class _Models:
            async def generate_content(self, *, model: str, contents: Any, config: Any = None) -> Any:
                outer.calls.append({"model": model, "contents": contents, "config": config})
                return type("FakeResponse", (), {"text": text})()

        class _Aio:
            models = _Models()

        self.aio = _Aio()


def captured_system_instruction(fake: FakeGeminiClient) -> str:
    """system_instruction ПЕРВОГО вызова LLM."""
    assert fake.calls, "LLM не был вызван"
    return fake.calls[0]["config"].system_instruction


def captured_contents(fake: FakeGeminiClient) -> str:
    """Текст contents ПЕРВОГО вызова LLM (строка или types.Content с одной частью-текстом)."""
    assert fake.calls, "LLM не был вызван"
    contents = fake.calls[0]["contents"]
    if isinstance(contents, str):
        return contents
    assert len(contents) == 1 and len(contents[0].parts) == 1
    return contents[0].parts[0].text


def make_lessons(items: list[dict[str, Any]]) -> list[Lesson]:
    """Занятия из JSON-описания во входных данных манифеста."""
    return [
        Lesson(
            subject=i["subject"],
            lesson_type=LessonType[i["lesson_type"]],
            date=date.fromisoformat(i["date"]),
            start_time=time.fromisoformat(i["start_time"]),
            end_time=time.fromisoformat(i["end_time"]),
            room=i["room"],
            group=i["group"],
        )
        for i in items
    ]


@pytest.fixture(autouse=True)
def forbid_real_gemini_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Реальный genai.Client запрещён: тесты снимка работают без сети (T-03-01)."""

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("реальный genai.Client запрещён в тестах снимка промптов")

    monkeypatch.setattr(genai, "Client", _boom)


@pytest.fixture
async def memory_db():
    db = Database(db_path=":memory:")
    await db.init_db()
    yield db
    await db.close()


def test_manifest_matches_files() -> None:
    assert MANIFEST["version"] == 1
    assert MANIFEST["prompts"], "манифест пуст"
    for key, rec in MANIFEST["prompts"].items():
        path = SNAP_DIR / rec["file"]
        assert path.is_file(), f"{key}: нет файла {rec['file']}"
        data = path.read_bytes()
        text = data.decode("utf-8")
        assert len(data) == rec["bytes"], f"{key}: длина в байтах"
        assert len(text) == rec["chars"], f"{key}: длина в символах"
        assert hashlib.sha256(data).hexdigest() == rec["sha256"], f"{key}: SHA-256"
        assert data.endswith(b"\n") == rec["ends_with_newline"], f"{key}: завершающий перевод строки"


def test_snapshot_files_tracked_by_git() -> None:
    """Эталоны не должны лежать в игнорируемом каталоге (.gitignore: data/)."""
    rel = [(SNAP_DIR / "MANIFEST.json").relative_to(REPO).as_posix()]
    rel += [(SNAP_DIR / rec["file"]).relative_to(REPO).as_posix() for rec in MANIFEST["prompts"].values()]
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", *rel],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"не отслеживаются git: {result.stderr}"


async def test_secretary_prompt_matches_snapshot(memory_db: Database) -> None:
    from src.brain.secretary_dialog import SecretaryDialogEngine

    inputs = prompt_inputs("secretary")
    engine = SecretaryDialogEngine(db=memory_db, api_key="x")
    fake = FakeGeminiClient()
    engine._client = fake
    # методист тоже не должен ходить в сеть; его вызовы идут в отдельный фейк
    engine.methodist._client = FakeGeminiClient()

    await engine.answer_user_message(user_id=inputs["user_id"], message_text=inputs["message_text"])

    assert captured_system_instruction(fake).encode("utf-8") == snapshot_bytes("secretary")


async def test_intent_router_prompt_matches_snapshot(memory_db: Database) -> None:
    from src.brain.intent_router import FastIntentRouter

    inputs = prompt_inputs("intent_router")
    router = FastIntentRouter(db=memory_db, api_key="x")
    fake = FakeGeminiClient('{"action": "secretary"}')
    router._client = fake

    await router.route(user_id=inputs["user_id"], message_text=inputs["message_text"])

    assert captured_system_instruction(fake).encode("utf-8") == snapshot_bytes("intent_router")


async def test_methodist_prompt_matches_snapshot(memory_db: Database) -> None:
    from src.brain.methodist import MethodistService

    inputs = prompt_inputs("methodist")
    service = MethodistService(memory_db, api_key="x")
    fake = FakeGeminiClient()
    service._client = fake

    await service.ask(inputs["question"])

    assert captured_system_instruction(fake).encode("utf-8") == snapshot_bytes("methodist")


async def test_methodist_scope_check_prompt_matches_snapshot(memory_db: Database) -> None:
    from src.brain.methodist import MethodistService

    inputs = prompt_inputs("methodist_scope_check")
    service = MethodistService(memory_db, api_key="x")
    fake = FakeGeminiClient('{"is_in_scope": false, "category": "out_of_scope", "reason": "x"}')
    service._client = fake

    await service.check_scope(inputs["question"])

    # вопрос без ключевых слов: проверка области обязана дойти до LLM
    assert len(fake.calls) == 1
    assert captured_contents(fake).encode("utf-8") == snapshot_bytes("methodist_scope_check")


async def test_reply_generator_prompt_matches_snapshot() -> None:
    from src.brain.reply_generator import ReplyGenerator

    inputs = prompt_inputs("reply_generator")
    generator = ReplyGenerator(api_key="x")
    fake = FakeGeminiClient()
    generator._client = fake

    await generator.generate_reply(inputs["email_data"])

    assert captured_system_instruction(fake).encode("utf-8") == snapshot_bytes("reply_generator")


async def test_debrief_call_matches_snapshot() -> None:
    from src.brain.debrief_parser import DebriefParser

    inputs = prompt_inputs("debrief_call")
    parser = DebriefParser(api_key="x")
    fake = FakeGeminiClient("{}")  # невалидный для схемы ответ: разбор уйдёт в детерминированный запасной путь
    parser._client = fake

    await parser.parse_debrief(inputs["transcript"], target_date=date.fromisoformat(inputs["target_date"]))

    assert captured_contents(fake).encode("utf-8") == snapshot_bytes("debrief_call")


def test_debrief_snapshot_has_no_trailing_newline_and_prefixes_call() -> None:
    debrief = snapshot_bytes("debrief")
    call = snapshot_bytes("debrief_call")
    assert not debrief.endswith(b"\n")
    assert call.startswith(debrief + b"\n\n")


async def test_morning_brief_prompt_matches_snapshot() -> None:
    from src.brain.summarizer import GeminiSummarizer

    inputs = prompt_inputs("morning_brief")
    summarizer = GeminiSummarizer(api_key="x")
    fake = FakeGeminiClient()
    summarizer._client = fake

    await summarizer.generate_morning_brief(
        target_date=date.fromisoformat(inputs["target_date"]),
        lessons=make_lessons(inputs["lessons"]),
        action_items=inputs["action_items"],
        timesheet_pacing=inputs["timesheet_pacing"],
    )

    assert captured_system_instruction(fake).encode("utf-8") == snapshot_bytes("morning_brief")


async def test_evening_digest_prompt_matches_snapshot() -> None:
    from src.brain.summarizer import GeminiSummarizer

    inputs = prompt_inputs("evening_digest")
    summarizer = GeminiSummarizer(api_key="x")
    fake = FakeGeminiClient()
    summarizer._client = fake

    await summarizer.generate_evening_digest(
        target_date=date.fromisoformat(inputs["target_date"]),
        email_stats=inputs["email_stats"],
        tomorrow_date=date.fromisoformat(inputs["tomorrow_date"]),
        tomorrow_lessons=make_lessons(inputs["tomorrow_lessons"]),
        action_items=inputs["action_items"],
    )

    assert captured_system_instruction(fake).encode("utf-8") == snapshot_bytes("evening_digest")
