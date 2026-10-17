from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STATUS_RU = {
    "pass": "ОК",
    "warn": "ВНИМАНИЕ",
    "fail": "ПРОВАЛ",
    "skip": "ПРОПУСК",
}


def to_markdown(scan: dict[str, Any]) -> str:
    meta = scan.get("meta") or {}
    ident = scan.get("identity") or {}
    score = scan.get("score") or {}
    lines = [
        f"# {meta.get('app', 'Helios')} — отчёт готовности",
        "",
        f"- Версия: {meta.get('version')}",
        f"- Хост: {meta.get('hostname')}",
        f"- Скан: {meta.get('scannedAt')}",
        f"- Длительность: {meta.get('elapsedMs')} мс",
        f"- Система: {ident.get('os')} ({ident.get('build')})",
        f"- CPU: {ident.get('cpu')}",
        f"- Машина: {ident.get('machine')}",
        f"- Оценка: **{score.get('value')} / 100 — {score.get('label')}**",
        "",
        "| Статус | Проверка | Значение | Вывод |",
        "|---|---|---|---|",
    ]
    for c in scan.get("checks") or []:
        lines.append(
            f"| {STATUS_RU.get(c.get('status'), c.get('status'))} | {c.get('title')} | {c.get('value') or '—'} | {c.get('summary')} |"
        )
    lines.append("")
    lines.append("Helios не обходит TPM и не патчит установщик. Это диагностика, не взлом.")
    return "\n".join(lines)


def default_export_dir() -> Path:
    home = Path.home()
    docs = home / "Documents"
    target = docs if docs.exists() else home
    folder = target / "Helios"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
