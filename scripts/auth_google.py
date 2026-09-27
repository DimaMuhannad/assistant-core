import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

def main() -> None:
    token_path = Path("token.json")
    creds = None

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired Google token...")
            creds.refresh(Request())
        else:
            if not Path("credentials.json").exists():
                print("Error: credentials.json not found in root directory!")
                return
            print("Initializing Google OAuth2 Flow...")
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(
                port=8088,
                prompt="consent",
                authorization_prompt_message="Please visit this URL in your browser to authorize access:\n{url}",
                success_message="Authorization successful! You may close this browser tab.",
                open_browser=True,
            )

        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
        print("Success! token.json has been generated and saved.")
    else:
        print("Valid token.json already exists.")

if __name__ == "__main__":
    main()
