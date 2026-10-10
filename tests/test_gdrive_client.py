"""Unit tests for GoogleDriveClient and server backup archiving."""

import inspect
import json
import tarfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.connectors.gdrive import client as gdrive_client_module
from src.connectors.gdrive.client import GoogleDriveClient


def test_is_configured_property(tmp_path: Path):
    token_file = tmp_path / "token.json"
    client = GoogleDriveClient(token_path=token_file)
    assert not client.is_configured

    # Token with calendar only
    token_file.write_text(json.dumps({"scopes": ["https://www.googleapis.com/auth/calendar"]}))
    assert not client.is_configured

    # Token with drive scope
    token_file.write_text(json.dumps({"scopes": ["https://www.googleapis.com/auth/drive"]}))
    assert client.is_configured


def test_create_server_backup_archive(tmp_path: Path):
    """Архив собирается из поддельного каталога ядра: боевые файлы и секреты не читаются."""
    fake_core = tmp_path / "fake_core"
    (fake_core / "data").mkdir(parents=True)
    db_bytes = b"synthetic-db-bytes"
    session_bytes = b"synthetic-session-bytes"
    env_bytes = b"SYNTHETIC_KEY=not-a-real-secret\n"
    (fake_core / "data" / "assistant.db").write_bytes(db_bytes)
    (fake_core / "data" / "assistant_worker.session").write_bytes(session_bytes)
    (fake_core / ".env").write_bytes(env_bytes)

    dest_dir = tmp_path / "uploads"
    dest_dir.mkdir(parents=True)

    archive_path = GoogleDriveClient.create_server_backup_archive(dest_dir=dest_dir, core_dir=fake_core)
    assert archive_path.exists()
    assert archive_path.name.endswith(".tar.gz")
    assert archive_path.stat().st_size > 0

    expected = {
        "assistant.db": db_bytes,
        "assistant_worker.session": session_bytes,
        "assistant-core.env": env_bytes,
    }
    with tarfile.open(archive_path, "r:gz") as tar:
        assert set(tar.getnames()) == set(expected)
        for name, content in expected.items():
            member = tar.extractfile(name)
            assert member is not None
            assert member.read() == content


def test_create_server_backup_archive_empty_without_db_and_env(tmp_path: Path):
    """include_db=False и include_env=False: архив валиден и пуст, core_dir не читается."""
    missing_core = tmp_path / "does_not_exist"
    dest_dir = tmp_path / "uploads"

    archive_path = GoogleDriveClient.create_server_backup_archive(
        dest_dir=dest_dir,
        include_db=False,
        include_env=False,
        core_dir=missing_core,
    )
    assert archive_path.exists()
    with tarfile.open(archive_path, "r:gz") as tar:
        assert tar.getnames() == []
    assert not missing_core.exists()


def test_create_server_backup_archive_default_core_dir_is_runtime_path():
    """Рантайм-вызов без аргументов по-прежнему смотрит в боевой каталог ядра."""
    default = inspect.signature(GoogleDriveClient.create_server_backup_archive).parameters["core_dir"].default
    assert str(default) == "/opt/assistant-core"


@patch("src.connectors.gdrive.client.build")
@patch("src.connectors.gdrive.client.Credentials")
def test_gdrive_search_and_folder_operations(mock_creds_cls, mock_build, tmp_path: Path):
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"scopes": ["https://www.googleapis.com/auth/drive"]}))

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds.valid = True
    mock_creds_cls.from_authorized_user_file.return_value = mock_creds

    mock_service = MagicMock()
    mock_build.return_value = mock_service

    # Mock folder query: existing folder
    mock_service.files().list().execute.return_value = {
        "files": [{"id": "folder_123", "name": "AI_Assistant_Backups"}]
    }

    client = GoogleDriveClient(token_path=token_file)
    folder_id = client.get_or_create_folder("AI_Assistant_Backups")
    assert folder_id == "folder_123"

    # Mock finding aadhk backup
    mock_service.files().list().execute.return_value = {
        "files": [
            {
                "id": "file_456",
                "name": "aadhk_timerecording_backup.db",
                "mimeType": "application/x-sqlite3",
                "modifiedTime": "2026-09-29T12:00:00Z",
            }
        ]
    }
    latest_file = client.find_latest_aadhk_backup()
    assert latest_file is not None
    assert latest_file["id"] == "file_456"
    assert "aadhk" in latest_file["name"]


def _all_paths(root: Path) -> set[Path]:
    return {p for p in root.rglob("*")}


def _make_sync_client(monkeypatch, tmp_path: Path, remote_name):
    """Клиент с подменённым Drive: поиск отдаёт remote_name, download_file пишет байты в путь."""
    uploads = tmp_path / "sandbox" / "uploads"
    uploads.mkdir(parents=True)
    monkeypatch.setattr(gdrive_client_module, "UPLOADS_DIR", uploads)

    client = GoogleDriveClient(token_path=tmp_path / "token.json")
    client.find_latest_aadhk_backup = MagicMock(
        return_value={"id": "file_1", "name": remote_name, "modifiedTime": "2026-09-29T12:00:00Z"}
    )
    download_calls: list[tuple[str, Path]] = []

    def fake_download(file_id, dest_path):
        dest = Path(dest_path)
        download_calls.append((file_id, dest))
        dest.write_bytes(b"synthetic-backup")
        return dest

    client.download_file = fake_download
    return client, uploads, download_calls


@pytest.mark.parametrize(
    "hostile_name",
    [
        "aadhk/../../../../escaped/evil.db",
        "../../x.db",
        "..",
        ".",
        "",
        "evil\x00.db",
        "..\\..\\x.db",
    ],
)
async def test_sync_rejects_hostile_remote_names(monkeypatch, tmp_path: Path, hostile_name: str):
    """CR-01 (T-02-07): враждебное имя с Drive даёт отказ, download_file не вызывается."""
    client, uploads, download_calls = _make_sync_client(monkeypatch, tmp_path, hostile_name)
    before = _all_paths(tmp_path)

    with patch("src.connectors.aadhk.parser.AadhkIngestionService") as service_cls:
        service_cls.return_value.ingest_backup_file = AsyncMock(return_value={})
        result = await client.sync_aadhk_from_drive(MagicMock())

    assert result["status"] == "error"
    assert "Недопустимое имя" in result["message"]
    assert download_calls == []
    assert _all_paths(tmp_path) == before
    assert list(uploads.iterdir()) == []


@pytest.mark.parametrize("link_kind", ["dir", "file"])
async def test_sync_rejects_symlink_pointing_outside_uploads(monkeypatch, tmp_path: Path, link_kind: str):
    """T-02-10: символьная ссылка в каталоге загрузок наружу не даёт записать файл за его пределы."""
    client, uploads, download_calls = _make_sync_client(monkeypatch, tmp_path, "evil.db")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = uploads / "gdrive_evil.db"
    if link_kind == "dir":
        link.symlink_to(outside, target_is_directory=True)
    else:
        target = outside / "victim.db"
        target.write_bytes(b"original")
        link.symlink_to(target)

    result = await client.sync_aadhk_from_drive(MagicMock())

    assert result["status"] == "error"
    assert download_calls == []
    assert [p.name for p in outside.iterdir()] in ([], ["victim.db"])
    if link_kind == "file":
        assert (outside / "victim.db").read_bytes() == b"original"


async def test_sync_safe_name_is_downloaded_into_uploads(monkeypatch, tmp_path: Path):
    """Безопасное имя скачивается в UPLOADS_DIR как gdrive_<имя>, контракт успеха сохранён."""
    client, uploads, download_calls = _make_sync_client(monkeypatch, tmp_path, "aadhk_backup.db")
    ingest = AsyncMock(return_value={"new_inserted_count": 2})

    with patch("src.connectors.aadhk.parser.AadhkIngestionService") as service_cls:
        service_cls.return_value.ingest_backup_file = ingest
        result = await client.sync_aadhk_from_drive(MagicMock())

    expected = (uploads / "gdrive_aadhk_backup.db").resolve()
    assert result["status"] == "success"
    assert result["file_name"] == "aadhk_backup.db"
    assert result["modified_time"] == "2026-09-29T12:00:00Z"
    assert result["ingestion_result"] == {"new_inserted_count": 2}
    assert download_calls == [("file_1", expected)]
    assert expected.read_bytes() == b"synthetic-backup"
    ingest.assert_awaited_once_with(expected)


async def test_sync_replaces_unsafe_characters_in_remote_name(monkeypatch, tmp_path: Path):
    """Символы вне [\\w.-] заменяются на «_», файл остаётся внутри каталога загрузок."""
    client, uploads, download_calls = _make_sync_client(monkeypatch, tmp_path, "my backup;$(x).db")

    with patch("src.connectors.aadhk.parser.AadhkIngestionService") as service_cls:
        service_cls.return_value.ingest_backup_file = AsyncMock(return_value={})
        result = await client.sync_aadhk_from_drive(MagicMock())

    assert result["status"] == "success"
    assert [p.name for p in uploads.iterdir()] == ["gdrive_my_backup___x_.db"]
