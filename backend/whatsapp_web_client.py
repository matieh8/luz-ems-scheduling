import os
import requests
from typing import Dict, Any

BRIDGE_PORT = os.environ.get("WHATSAPP_BRIDGE_PORT", "8020")
BRIDGE_URL = os.environ.get("WHATSAPP_BRIDGE_URL", f"http://127.0.0.1:{BRIDGE_PORT}")


def get_status() -> Dict[str, Any]:
    try:
        r = requests.get(f"{BRIDGE_URL}/status", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"ready": False, "status": "bridge_offline", "error": str(e)}


class BridgeNotReady(Exception):
    """The bridge process is up but WhatsApp is not connected (no pairing yet, or reconnecting)."""


def send_message(to: str, message: str) -> Dict[str, Any]:
    r = requests.post(f"{BRIDGE_URL}/send", json={"to": to, "message": message}, timeout=30)
    if r.status_code == 503:
        raise BridgeNotReady("WhatsApp is not connected on this server. Open Settings → Messaging and scan the QR code if one is shown.")
    if not r.ok:
        try:
            detail = r.json().get("error") or r.text
        except ValueError:
            detail = r.text
        raise RuntimeError(f"WhatsApp bridge error {r.status_code}: {detail}")
    return r.json()
