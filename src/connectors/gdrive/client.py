"""Google Drive client for file upload/download and AADHk sync."""

import asyncio
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from src import config
from src.storage.db import Database

logger = logging.getLogger(__name__)

# Каталог, куда складываются скачанные с Google Drive файлы. Читается в момент вызова
# (тесты подменяют его через monkeypatch), демон пишет сюда от root (CR-01, D-17).
UPLOADS_DIR = Path("/opt/chat-app/uploads")

_UNSAFE_NAME_CHARS = re.compile(r"[^\w.-]")


def _safe_upload_path(remote_name: Any) -> Path | None:
    """Построить путь внутри UPLOADS_DIR по имени файла с Drive или вернуть None (отказ).

    Имя приходит извне (в том числе из файла, которым с владельцем поделились), а демон пишет
    от root, поэтому имя не доверяется: разделители пути, «..», пустое имя и нулевой байт
    отвергаются, прочие символы вне [\\w.-] заменяются на «_», а родитель назначения после
    resolve() обязан совпасть с UPLOADS_DIR.resolve() (символьная ссылка наружу даёт отказ).
    """
    try:
        if not isinstance(remote_name, str):
            return None
        if "\x00" in remote_name or "/" in remote_name or "\\" in remote_name:
            return None
        name = Path(remote_name).name
        if name in ("", ".", ".."):
            return None
        safe_name = _UNSAFE_NAME_CHARS.sub("_", name)
        uploads_root = UPLOADS_DIR.resolve()
        dest = (UPLOADS_DIR / f"gdrive_{safe_name}").resolve()
        if dest.parent != uploads_root:
            return None
        return dest
    except (ValueError, OSError):
        return None


DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive",
]


class GoogleDriveClient:
    """Handles interaction with Google Drive v3 API."""

    def __init__(
        self,
        token_path: str | Path = "/opt/assistant-core/token.json",
        credentials_path: str | Path = "/opt/assistant-core/credentials.json",
    ) -> None:
        self.token_path = Path(token_path)
        self.credentials_path = Path(credentials_path)
        self._service: Any = None

    @property
    def is_configured(self) -> bool:
        if not self.token_path.exists():
            return False
        try:
            with open(self.token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            scopes = data.get("scopes", [])
            return any("drive" in s for s in scopes)
        except Exception:
            return False

    def get_service(self) -> Any:
        """Returns authenticated Google Drive v3 service."""
        if self._service is not None:
            return self._service

        if not self.token_path.exists():
            raise FileNotFoundError(f"Token file not found at {self.token_path}")

        creds = Credentials.from_authorized_user_file(str(self.token_path), DRIVE_SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(self.token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

        self._service = build("drive", "v3", credentials=creds)
        return self._service

    def search_files(
        self,
        query: str = "trashed = false",
        page_size: int = 15,
        fields: str = "files(id, name, mimeType, size, modifiedTime)",
    ) -> list[dict[str, Any]]:
        """Search files on Google Drive."""
        service = self.get_service()
        results = (
            service.files()
            .list(q=query, pageSize=page_size, fields=fields, orderBy="modifiedTime desc")
            .execute()
        )
        return results.get("files", [])

    def find_latest_aadhk_backup(self) -> dict[str, Any] | None:
        """Find the latest AADHk SQLite backup file on Google Drive."""
        service = self.get_service()
        # 1. First check if dedicated com.aadhk.time folder exists
        folder_q = "name = 'com.aadhk.time' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        folders = service.files().list(q=folder_q, fields="files(id, name)").execute().get("files", [])
        if folders:
            folder_id = folders[0]["id"]
            files_q = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
            folder_files = service.files().list(
                q=files_q,
                fields="files(id, name, mimeType, size, modifiedTime)",
                orderBy="modifiedTime desc",
                pageSize=5,
            ).execute().get("files", [])
            if folder_files:
                return folder_files[0]

        # 2. General search excluding folders
        queries = [
            "name contains 'timetracker' and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
            "name contains 'aadhk' and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
            "name contains 'timerecording' and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
            "name contains '.db' and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
        ]
        for q in queries:
            files = self.search_files(query=q, page_size=5)
            non_folders = [f for f in files if f.get("mimeType") != "application/vnd.google-apps.folder"]
            if non_folders:
                return non_folders[0]
        return None

    def download_file(self, file_id: str, dest_path: str | Path) -> Path:
        """Download file by ID to destination path."""
        service = self.get_service()
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logger.debug("Download %d%%", int(status.progress() * 100))

        fh.seek(0)
        with open(dest, "wb") as f:
            f.write(fh.read())

        logger.info("Downloaded Google Drive file %s to %s", file_id, dest)
        return dest

    def get_or_create_folder(self, folder_name: str = "AI_Assistant_Backups") -> str:
        """Get or create root folder on Google Drive."""
        service = self.get_service()
        q = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]

        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder = service.files().create(body=folder_metadata, fields="id").execute()
        logger.info("Created folder '%s' with ID %s", folder_name, folder["id"])
        return folder["id"]

    def upload_file(
        self,
        local_path: str | Path,
        folder_name: str = "AI_Assistant_Backups",
        remote_filename: str | None = None,
        mime_type: str = "application/gzip",
    ) -> dict[str, Any]:
        """Upload a file to Google Drive folder."""
        service = self.get_service()
        p = Path(local_path)
        if not p.is_file():
            raise FileNotFoundError(f"Local file to upload not found: {local_path}")

        folder_id = self.get_or_create_folder(folder_name)
        file_metadata = {
            "name": remote_filename or p.name,
            "parents": [folder_id],
        }
        media = MediaFileUpload(str(p), mimetype=mime_type, resumable=True)
        uploaded = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id, name, size, webViewLink")
            .execute()
        )
        logger.info("Uploaded %s to Google Drive (ID: %s)", p.name, uploaded.get("id"))
        return uploaded

    async def sync_aadhk_from_drive(self, db: Database) -> dict[str, Any]:
        """Find latest AADHk backup on Google Drive, download it, and run AadhkIngestionService."""
        from src.connectors.aadhk.parser import AadhkIngestionService

        # Блокирующие вызовы Google API уходят в поток, чтобы не замораживать event loop (WR-01).
        backup_file = await asyncio.to_thread(self.find_latest_aadhk_backup)
        if not backup_file:
            logger.info("No AADHk backup found on Google Drive.")
            return {"status": "not_found", "message": "No backup file found on Google Drive"}

        file_id = backup_file["id"]
        remote_name = backup_file["name"]
        local_dest = _safe_upload_path(remote_name)
        if local_dest is None:
            logger.warning("Rejected unsafe Google Drive file name: %s", repr(remote_name)[:80])
            return {
                "status": "error",
                "message": "Недопустимое имя файла на Google Drive, загрузка отклонена",
            }

        await asyncio.to_thread(self.download_file, file_id, local_dest)
        ingestion = AadhkIngestionService(db)
        res = await ingestion.ingest_backup_file(local_dest)

        return {
            "status": "success",
            "file_name": remote_name,
            "modified_time": backup_file.get("modifiedTime"),
            "ingestion_result": res,
        }
