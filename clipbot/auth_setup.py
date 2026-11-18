"""Run ONCE on your own computer to connect the megapithucs channel.

    pip install google-auth-oauthlib
    python -m clipbot.auth_setup path/to/client_secret.json

A browser opens -> sign in -> pick the megapithucs channel (red gorilla).
It prints the three values to paste into GitHub secrets.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from clipbot.youtube_api import SCOPES

if __name__ == "__main__":
    secret_file = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
    flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    info = json.load(open(secret_file))
    info = info.get("installed") or info.get("web")
    print("\nAdd these as GitHub repository secrets (Settings > Secrets and variables > Actions):\n")
    print("YT_CLIENT_ID     =", info["client_id"])
    print("YT_CLIENT_SECRET =", info["client_secret"])
    print("YT_REFRESH_TOKEN =", creds.refresh_token)
    print("\nKeep these private. Don't paste them in any chat.")
