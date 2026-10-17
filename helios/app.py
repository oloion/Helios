from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import webview

from helios import __version__
from helios.engine import run_scan
from helios.report import default_export_dir, to_markdown
from helios.telemetry import snapshot


def resource_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


def _clipboard(text: str) -> None:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
    except Exception:
        pass


class Bridge:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict | None = None

    def ping(self) -> str:
        return f"helios-{__version__}"

    def telemetry(self) -> dict:
        return snapshot()

    def scan(self) -> dict:
        with self._lock:
            self._last = run_scan()
            return self._last

    def last(self) -> dict | None:
        return self._last

    def copy_markdown(self) -> str:
        if not self._last:
            return "no-scan"
        text = to_markdown(self._last)
        _clipboard(text)
        window = webview.windows[0]
        window.evaluate_js(
            f"navigator.clipboard.writeText({json.dumps(text)}).catch(()=>{{}})"
        )
        return "ok"

    def export(self) -> dict:
        if not self._last:
            return {"ok": False, "error": "Сначала запустите скан."}
        folder = default_export_dir()
        json_path = folder / "helios-report.json"
        md_path = folder / "helios-report.md"
        json_path.write_text(
            json.dumps(self._last, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        md_path.write_text(to_markdown(self._last), encoding="utf-8")
        return {"ok": True, "json": str(json_path), "md": str(md_path)}

    def minimize(self) -> None:
        webview.windows[0].minimize()

    def close(self) -> None:
        webview.windows[0].destroy()


def run() -> None:
    ui = resource_path("ui", "index.html")
    bridge = Bridge()
    webview.create_window(
        "Helios",
        url=str(ui),
        js_api=bridge,
        width=1320,
        height=860,
        min_size=(1100, 720),
        background_color="#07080c",
        frameless=True,
        easy_drag=False,
    )
    webview.start(debug=False)
