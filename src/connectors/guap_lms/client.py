"""GUAP LMS (pro.guap.ru) session client and task parser."""

import json
import logging
import re
from pathlib import Path
from typing import Any
import requests
from bs4 import BeautifulSoup

from src import config

logger = logging.getLogger(__name__)


class GuapLmsClient:
    """Client for interacting with GUAP instructor portal pro.guap.ru via Keycloak SSO."""

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.email = config.GUAP_EMAIL if email is None else email
        self.password = (
            (config.GUAP_LK_PASSWORD or config.GUAP_PASSWORD)
            if password is None
            else password
        )
        self.timeout = timeout

        self.base_url = "https://pro.guap.ru"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    @property
    def is_configured(self) -> bool:
        """Checks if login credentials are provided in configuration."""
        return bool(self.email and self.password)

    def is_authenticated(self) -> bool:
        """Verify if current session cookie is valid and authorized."""
        try:
            r = self.session.get(
                f"{self.base_url}/inside/profile",
                timeout=self.timeout,
                allow_redirects=False,
            )
            return r.status_code == 200
        except Exception as e:
            logger.debug("Failed authentication check: %s", e)
            return False

    def login(self) -> bool:
        """Authenticate into pro.guap.ru via Keycloak SSO."""
        if not self.is_configured:
            logger.error("GUAP credentials not configured.")
            return False

        try:
            logger.info("Initiating Keycloak SSO login for %s...", self.email)
            # 1. Hit oauth entry point to get redirected to sso.guap.ru
            r_oauth = self.session.get(
                f"{self.base_url}/oauth/login",
                timeout=self.timeout,
                allow_redirects=True,
            )
            soup = BeautifulSoup(r_oauth.text, "html.parser")
            form = soup.find("form")
            if not form:
                logger.error("Could not find Keycloak login form at %s", r_oauth.url)
                return False

            action_url = form.get("action")
            if not action_url:
                logger.error("Keycloak form missing action URL.")
                return False

            # 2. Post credentials to Keycloak
            post_data = {
                "username": self.email,
                "password": self.password,
                "rememberMe": "on",
                "credentialId": "",
            }

            r_post = self.session.post(
                action_url,
                data=post_data,
                timeout=self.timeout,
                allow_redirects=True,
            )

            if "pro.guap.ru" in str(r_post.url) and "sso.guap.ru" not in str(r_post.url):
                logger.info("Successfully authenticated to pro.guap.ru (URL: %s)", r_post.url)
                return True

            # If still on sso page, parse error
            soup_err = BeautifulSoup(r_post.text, "html.parser")
            alert = soup_err.find(class_="alert") or soup_err.find(class_="kc-feedback-text")
            err_msg = alert.get_text(strip=True) if alert else "Unknown auth failure"
            logger.error("Keycloak login failed: %s", err_msg)
            return False

        except Exception as e:
            logger.exception("Error logging in to pro.guap.ru: %s", e)
            return False

    def ensure_authenticated(self) -> None:
        """Ensure session is active or perform login."""
        if not self.is_authenticated():
            if not self.login():
                raise ConnectionError("Failed to authenticate into pro.guap.ru.")

    def list_tasks(self, semester: int | str = 28) -> list[dict[str, Any]]:
        """List instructor tasks for semester from pro.guap.ru."""
        self.ensure_authenticated()
        url = f"{self.base_url}/inside/professor/tasks"
        params = {"semesters": str(semester)} if semester else None

        r = self.session.get(url, params=params, timeout=self.timeout)
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        if not table:
            return []

        tasks: list[dict[str, Any]] = []
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 8:
                continue

            # Column 1: Ordernum
            ordernum = tds[1].get_text(strip=True)

            # Column 2: Subject & Group
            subject_txt = tds[2].get_text(" ", strip=True)

            # Column 3: Title & Link
            link_tag = tds[3].find("a")
            title = link_tag.get_text(strip=True) if link_tag else tds[3].get_text(strip=True)
            href = link_tag.get("href") if link_tag else ""
            task_id = None
            if href:
                m = re.search(r"/tasks/(\d+)/show", href)
                if m:
                    task_id = int(m.group(1))

            # Column 4: Type
            task_type = tds[4].get_text(strip=True)

            # Column 5: Deadline
            deadline = tds[5].get_text(strip=True)

            # Column 6: Visibility to student
            vis_td = tds[6]
            is_public = False
            eye_icon = vis_td.find("i")
            if eye_icon:
                classes = eye_icon.get("class", [])
                title_attr = eye_icon.get("title", "")
                if "text-success" in classes or "Виден" in title_attr:
                    is_public = True

            # Column 7: Updated
            updated_at = tds[7].get_text(strip=True)

            tasks.append({
                "id": task_id,
                "ordernum": ordernum,
                "subject": subject_txt,
                "title": title,
                "task_type": task_type,
                "deadline": deadline,
                "is_public": is_public,
                "updated_at": updated_at,
                "link": href,
            })

        logger.info("Parsed %d tasks from pro.guap.ru for semester %s", len(tasks), semester)
        return tasks

    def get_task_details(self, task_id: int | str) -> dict[str, Any]:
        """Fetch task details and submitted student reports."""
        self.ensure_authenticated()
        url = f"{self.base_url}/inside/professor/tasks/{task_id}/show"
        r = self.session.get(url, timeout=self.timeout)
        soup = BeautifulSoup(r.text, "html.parser")

        title = ""
        subject = ""
        task_type = ""
        completed_stats = ""
        pending_stats = ""

        for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            txt = h.get_text(strip=True)
            if txt.startswith("Дисциплина:"):
                subject = txt.removeprefix("Дисциплина:").strip()
            elif txt.startswith("Тип:"):
                task_type = txt.removeprefix("Тип:").strip()
            elif txt.startswith("Выполнили:"):
                completed_stats = txt.removeprefix("Выполнили:").strip()
            elif txt.startswith("Ожидают проверки:"):
                pending_stats = txt.removeprefix("Ожидают проверки:").strip()
            elif not title and txt and "Личный кабинет" not in txt:
                title = txt

        # Parse student submissions table
        reports: list[dict[str, Any]] = []
        table = soup.find("table")
        if table:
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 5:
                    continue

                student_name = tds[1].get_text(strip=True)
                group_name = tds[2].get_text(strip=True)
                status = tds[3].get_text(strip=True)
                upload_date = tds[4].get_text(strip=True)
                check_date = tds[5].get_text(strip=True) if len(tds) > 5 else ""

                download_url = ""
                for a in tr.find_all("a"):
                    ahref = a.get("href", "")
                    if "download" in ahref:
                        download_url = ahref
                        break

                rep_id = None
                if download_url:
                    m = re.search(r"/reports/(\d+)/download", download_url)
                    if m:
                        rep_id = int(m.group(1))

                reports.append({
                    "report_id": rep_id,
                    "student_name": student_name,
                    "group": group_name,
                    "status": status,
                    "upload_date": upload_date,
                    "check_date": check_date,
                    "download_url": download_url,
                })

        return {
            "task_id": int(task_id),
            "title": title,
            "subject": subject,
            "task_type": task_type,
            "completed_stats": completed_stats,
            "pending_stats": pending_stats,
            "reports_count": len(reports),
            "reports": reports,
        }

    def create_task(
        self,
        name: str,
        subject_id: str | int,
        group_ids: list[str | int],
        semester_id: str | int = 28,
        task_type_id: str | int = 2,
        description: str = "",
        markpoint: int = 10,
        ordernum: int = 1,
        harddeadline: str = "2026-10-31",
        is_public: bool = False,
        report_required: bool = True,
        extensions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new task on pro.guap.ru.

        Note:
            is_public defaults to False for safety (task will NOT be visible to students).
        """
        self.ensure_authenticated()
        # 1. Fetch create page to get CSRF token and store URL
        r_create = self.session.get(f"{self.base_url}/inside/professor/tasks/create", timeout=self.timeout)
        soup = BeautifulSoup(r_create.text, "html.parser")
        store_form = None
        for f in soup.find_all("form"):
            if "store" in str(f.get("action")):
                store_form = f
                break

        if not store_form:
            raise RuntimeError("Could not locate store form on /inside/professor/tasks/create")

        action_url = store_form.get("action")
        if action_url.startswith("/"):
            action_url = self.base_url + action_url

        csrf_token = store_form.find("input", {"name": "token"}).get("value")

        # 2. Build form payload
        data: dict[str, Any] = {
            "token": csrf_token,
            "semesters": str(semester_id),
            "subjects[]": [str(subject_id)],
            "types": str(task_type_id),
            "groups[]": [str(g) for g in group_ids],
            "name": name,
            "description": description,
            "markpoint": str(markpoint),
            "extensions[]": extensions or ["0"],
            "url": "",
            "ordernum": str(ordernum),
            "harddeadline": harddeadline,
            "file-deleted": "",
        }

        if report_required:
            data["reportRequired"] = "on"

        # Explicitly control student visibility
        if is_public:
            data["public"] = "on"

        files = {
            "file": ("", b""),
        }

        logger.info("Submitting task '%s' (is_public=%s) to pro.guap.ru...", name, is_public)
        resp = self.session.post(action_url, data=data, files=files, timeout=self.timeout)

        created_id = None
        m = re.search(r"/tasks/(\d+)/show", resp.url)
        if m:
            created_id = int(m.group(1))

        return {
            "status": "success" if resp.status_code == 200 else "error",
            "status_code": resp.status_code,
            "created_id": created_id,
            "url": resp.url,
            "name": name,
            "is_public": is_public,
        }

    def download_student_report(self, download_path_or_id: str | int, dest_file: str | Path) -> Path:
        """Download student's submitted report file (PDF, docx, etc.) for AI analysis."""
        self.ensure_authenticated()
        if isinstance(download_path_or_id, int) or download_path_or_id.isdigit():
            url = f"{self.base_url}/inside/professor/reports/{download_path_or_id}/download"
        else:
            url = (
                self.base_url + download_path_or_id
                if download_path_or_id.startswith("/")
                else download_path_or_id
            )

        p = Path(dest_file)
        p.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Downloading student report from %s to %s...", url, p)
        with self.session.get(url, stream=True, timeout=self.timeout) as r:
            r.raise_for_status()
            with open(p, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        logger.info("Downloaded %d bytes to %s", p.stat().st_size, p)
        return p

    def get_disciplines(self) -> list[dict[str, Any]]:
        """Fetch available instructor disciplines and groups from create page."""
        self.ensure_authenticated()
        r = self.session.get(f"{self.base_url}/inside/professor/tasks/create", timeout=self.timeout)
        m = re.search(r"const subjects = ({[\s\S]*?});\s*const disciplines", r.text)
        if not m:
            return []

        try:
            data = json.loads(m.group(1))
            return list(data.values())
        except Exception as e:
            logger.warning("Failed parsing subjects JSON: %s", e)
            return []
