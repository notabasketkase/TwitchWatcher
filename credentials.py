"""
credentials.py — Client Secret storage and Twitch app-token retrieval.

The Client Secret lives in Windows Credential Manager (via keyring), never on
disk. get_app_token exchanges the id+secret for a short-lived app token.

(Named credentials.py, not secrets.py, to avoid shadowing Python's stdlib
`secrets` module.)
"""

import requests

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

KEYRING_SERVICE  = "TwitchWatcher"
KEYRING_USERNAME = "client_secret"

TOKEN_URL = "https://id.twitch.tv/oauth2/token"


def store_secret(secret):
    if KEYRING_AVAILABLE:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, secret)


def load_secret():
    if KEYRING_AVAILABLE:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or ""
    return ""


def delete_secret():
    if KEYRING_AVAILABLE:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception:
            pass


def get_app_token(client_id, client_secret):
    resp = requests.post(TOKEN_URL, params={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]
