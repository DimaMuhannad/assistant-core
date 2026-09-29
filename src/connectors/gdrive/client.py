"""Google Drive client for off-server backup archiving and AADHk sync."""

import io
import json
import logging
import os
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from src import config
from src.storage.db import Database

logger = logging.getLogger(__name__)

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

    @staticmethod
    def create_server_backup_archive(
        dest_dir: str | Path = "/opt/chat-app/uploads",
        include_db: bool = True,
        include_env: bool = True,
        include_uploads: bool = False,
    ) -> Path:
        """Create a compressed .tar.gz archive of sensitive non-git server data."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_folder = Path(dest_dir)
        dest_folder.mkdir(parents=True, exist_ok=True)
        archive_path = dest_folder / f"server_backup_{timestamp}.tar.gz"

        files_to_pack: list[tuple[str, str]] = []
        if include_db:
            db_path = "/opt/assistant-core/data/assistant.db"
            if os.path.exists(db_path):
                files_to_pack.append((db_path, "assistant.db"))
            session_path = "/opt/assistant-core/data/assistant_worker.session"
            if os.path.exists(session_path):
                files_to_pack.append((session_path, "assistant_worker.session"))

        if include_env:
            env_core = "/opt/assistant-core/.env"
            if os.path.exists(env_core):
                files_to_pack.append((env_core, "assistant-core.env"))

        with tarfile.open(archive_path, "w:gz") as tar:
            for src_file, arc_name in files_to_pack:
                tar.add(src_file, arcname=arc_name)
                logger.debug("Added %s to archive as %s", src_file, arc_name)

        logger.info("Created server backup archive: %s (size: %d bytes)", archive_path, archive_path.stat().st_size)
        return archive_path

    async def backup_server_data_to_drive(
        self,
        folder_name: str = "AI_Assistant_Backups",
    ) -> dict[str, Any]:
        """Full cycle: archive server data and upload to Google Drive."""
        archive_path = self.create_server_backup_archive()
        try:
            uploaded = self.upload_file(archive_path, folder_name=folder_name)
            return {
                "archive_path": str(archive_path),
                "drive_file_id": uploaded.get("id"),
                "file_name": uploaded.get("name"),
                "size_bytes": archive_path.stat().st_size,
                "drive_link": uploaded.get("webViewLink", ""),
            }
        finally:
            # Clean up local backup archive from uploads
            if archive_path.exists():
                try:
                    archive_path.unlink()
                except Exception:
                    pass

    async def sync_aadhk_from_drive(self, db: Database) -> dict[str, Any]:
        """Find latest AADHk backup on Google Drive, download it, and run AadhkIngestionService."""
        from src.connectors.aadhk.parser import AadhkIngestionService

        backup_file = self.find_latest_aadhk_backup()
        if not backup_file:
            logger.info("No AADHk backup found on Google Drive.")
            return {"status": "not_found", "message": "No backup file found on Google Drive"}

        file_id = backup_file["id"]
        remote_name = backup_file["name"]
        local_dest = Path(f"/opt/chat-app/uploads/gdrive_{remote_name}")

        self.download_file(file_id, local_dest)
        ingestion = AadhkIngestionService(db)
        res = await ingestion.ingest_backup_file(local_dest)

        return {
            "status": "success",
            "file_name": remote_name,
            "modified_time": backup_file.get("modifiedTime"),
            "ingestion_result": res,
        }
