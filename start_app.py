from __future__ import annotations

import multiprocessing
import os
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from app import app


HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}/"


def configure_windowed_logging() -> None:
    # Windowed EXE içinde görünmeyen hatalar AppData altındaki log dosyasına yazılır.
    if not getattr(sys, "frozen", False):
        return

    log_dir = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "ErgeneAI" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "startup.log"
    stream = log_file.open("a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream
    print("\n--- Uygulama başlatılıyor ---")


def is_server_ready() -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


def run_server() -> None:
    # Uvicorn tek süreçte çalışır; analiz tarafı EXE içinde thread havuzuna geçer.
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


def open_browser_when_ready() -> None:
    deadline = time.time() + 45
    while time.time() < deadline:
        if is_server_ready():
            webbrowser.open(URL)
            print(f"Tarayıcı açıldı: {URL}")
            return
        time.sleep(0.5)

    print(f"Sunucu zamanında hazır olmadı: {URL}")


def main() -> int:
    multiprocessing.freeze_support()
    configure_windowed_logging()

    if is_server_ready():
        webbrowser.open(URL)
        return 0

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    open_browser_when_ready()

    try:
        while server_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("Uygulama kullanıcı tarafından kapatıldı.")
    except Exception:
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
