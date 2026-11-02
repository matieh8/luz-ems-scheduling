import os
import requests
from typing import Optional, Dict, Any

BRIDGE_URL = os.environ.get("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:8020")


def get_status() -> Dict[str, Any]:
    try:
        r = requests.get(f"{BRIDGE_URL}/status", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"ready": False, "status": "bridge_offline", "error": str(e)}


def send_message(to: str, message: str) -> Dict[str, Any]:
    r = requests.post(
        f"{BRIDGE_URL}/send",
        json={"to": to, "message": message},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
