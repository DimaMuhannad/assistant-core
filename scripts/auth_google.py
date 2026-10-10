"""Interactive helper to authorize Google Calendar, Gmail, and Google Drive."""

import json
import os
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive",
]


def _print_privacy_notice() -> None:
    """Предупреждение PRIV-01 в stderr: текст из данных персоны, при сбое нейтральный запасной."""
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from src.persona.notices import email_ai_notice

    try:
        from src.persona.loader import load_persona

        text = email_ai_notice(load_persona())
    except Exception:
        text = email_ai_notice(None)
    print(f"🔒 Приватность: {text}", file=sys.stderr)


def main() -> None:
    _print_privacy_notice()
    token_path = Path("/opt/assistant-core/token.json")
    creds_path = Path("/opt/assistant-core/credentials.json")

    if not creds_path.exists():
        print(f"Error: credentials.json not found at {creds_path}!")
        return

    # Check if existing token already has drive scope
    if token_path.exists():
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing_scopes = data.get("scopes", [])
            if any("drive" in s for s in existing_scopes):
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
                if creds and creds.valid:
                    print("Valid token.json with Google Drive already exists!")
                    return
                elif creds and creds.expired and creds.refresh_token:
                    print("Refreshing expired Google token...")
                    creds.refresh(Request())
                    with open(token_path, "w", encoding="utf-8") as token_file:
                        token_file.write(creds.to_json())
                    print("Success! Refreshed token saved.")
                    return
        except Exception as e:
            print(f"Existing token could not be refreshed with Drive scope: {e}")

    print("Initializing Google OAuth2 Flow with Drive, Calendar, and Gmail...")
    redirect_uri = "http://localhost:8088/"
    flow = InstalledAppFlow.from_client_secrets_file(
        str(creds_path),
        SCOPES,
        redirect_uri=redirect_uri,
    )

    pending_file = Path("/opt/assistant-core/data/oauth_pending.json")

    if "--get-url" in sys.argv:
        auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pending_file, "w", encoding="utf-8") as pf:
            json.dump({"state": state, "code_verifier": getattr(flow, "code_verifier", None)}, pf)
        print("\n" + "=" * 60)
        print("🔗 Ссылка для авторизации Google Drive:")
        print(auth_url)
        print("=" * 60 + "\n")
        return

    if "--exchange" in sys.argv:
        idx = sys.argv.index("--exchange")
        if idx + 1 >= len(sys.argv):
            print("Error: --exchange requires a code or redirect URL argument.")
            return
        user_input = sys.argv[idx + 1].strip()
        if pending_file.exists():
            try:
                with open(pending_file, "r", encoding="utf-8") as pf:
                    pending_data = json.load(pf)
                if pending_data.get("code_verifier"):
                    flow.code_verifier = pending_data["code_verifier"]
                if pending_data.get("state"):
                    flow.oauth2session._state = pending_data["state"]
            except Exception as e:
                print(f"Warning: could not read pending auth data: {e}")

        if "code=" in user_input:
            import urllib.parse
            parsed = urllib.parse.urlparse(user_input)
            qs = urllib.parse.parse_qs(parsed.query)
            code = qs.get("code", [user_input])[0]
        else:
            code = user_input
        print("Exchanging authorization code for tokens...")
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
        if pending_file.exists():
            pending_file.unlink(missing_ok=True)
        print(f"Success! token.json saved to {token_path} with Google Drive scope.")
        return


    # Use out-of-band / console flow or local server
    if "--console" in sys.argv:
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        print("\n" + "=" * 60)
        print("Please open this link in your browser:")
        print(auth_url)
        print("=" * 60 + "\n")
        code = input("Enter the authorization code here: ").strip()
        flow.fetch_token(code=code)
        creds = flow.credentials
    else:
        # Local redirect or URL paste
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        print("\n" + "=" * 60)
        print("🔗 Ссылка для авторизации Google Drive:")
        print(auth_url)
        print("=" * 60 + "\n")
        try:
            creds = flow.run_local_server(
                port=8088,
                prompt="consent",
                authorization_prompt_message="Open URL:\n{url}",
                success_message="Authorization successful! You can close this tab.",
                open_browser=False,
            )
        except Exception as se:
            print(f"Local server stopped or port busy ({se}).")
            return

    with open(token_path, "w", encoding="utf-8") as token_file:
        token_file.write(creds.to_json())
    print(f"Success! token.json saved to {token_path} with Google Drive scope.")


if __name__ == "__main__":
    main()

