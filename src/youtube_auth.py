from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle
import os

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

TOKEN_PATH = os.path.join("auth", "token.pickle")
CLIENT_SECRETS_PATH = os.path.join("auth", "client_secret.json")

def get_youtube_service():
    creds = None

    os.makedirs("auth", exist_ok=True)

    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as token:
            creds = pickle.load(token)

    if not creds:
        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRETS_PATH,
            SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "wb") as token:
            pickle.dump(creds, token)

    return build("youtube", "v3", credentials=creds)