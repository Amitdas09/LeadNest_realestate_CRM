"""Keep a public HTTPS tunnel to the local app and keep Meta's webhook pointed at it.

Free tunnels (localhost.run) change their address from time to time. This runs
the tunnel through the ssh client built into Windows, watches for new
addresses, and re-registers the WhatsApp webhook each time. If the tunnel
drops, it reconnects.

    python -m app.tunnel
"""

import json
import subprocess
import time
from pathlib import Path

from app.cli import whatsapp_webhook
from app.core.config import PROJECT_ROOT

URL_FILE = PROJECT_ROOT / "tools" / "tunnel_url.txt"
CMD = ["ssh", "-T", "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=30",
       "-o", "ServerAliveCountMax=3", "-o", "ExitOnForwardFailure=yes",
       "-R", "80:127.0.0.1:8000", "nokey@localhost.run", "--", "--output", "json"]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def run_once() -> None:
    current = None
    proc = subprocess.Popen(CMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        address = (event.get("data") or {}).get("address")
        if not address or address == current:
            continue
        current = address
        url = f"https://{address}"
        Path(URL_FILE).parent.mkdir(exist_ok=True)
        URL_FILE.write_text(url)
        log(f"tunnel address: {url}")
        time.sleep(2)  # let the tunnel settle before Meta calls it to verify
        # Keep trying (e.g. the app may be restarting): Meta verifies the URL by calling it.
        for attempt in range(1, 41):
            if whatsapp_webhook(url) == 0:
                log("webhook registered with Meta")
                break
            log(f"webhook registration failed (attempt {attempt}); retrying in 15 s")
            time.sleep(15)
        else:
            log("WARNING: could not register webhook with Meta after 10 minutes")
    proc.wait()
    log(f"tunnel exited (code {proc.returncode})")


def main() -> None:
    while True:
        try:
            run_once()
        except Exception as exc:  # keep the tunnel alive no matter what
            log(f"tunnel error: {exc!r}")
        log("reconnecting in 5 s")
        time.sleep(5)


if __name__ == "__main__":
    main()
