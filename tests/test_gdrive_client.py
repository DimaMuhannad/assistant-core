"""Unit tests for GoogleDriveClient and server backup archiving."""

import inspect
import json
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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
