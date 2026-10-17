from __future__ import annotations

import shutil
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore


def snapshot() -> dict[str, Any]:
    if psutil is None:
        return {"cpu": 0, "ram": 0, "ramText": "psutil?", "disk": 0, "diskText": "—"}
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    try:
        du = shutil.disk_usage("C:\\")
        disk_used = 100 * (1 - du.free / du.total) if du.total else 0
        disk_text = f"{du.free / 1024**3:.0f} ГБ свободно"
    except OSError:
        disk_used = 0
        disk_text = "—"
    return {
        "cpu": round(cpu, 1),
        "ram": round(vm.percent, 1),
        "ramText": f"{vm.used / 1024**3:.1f} / {vm.total / 1024**3:.1f} ГБ",
        "disk": round(disk_used, 1),
        "diskText": disk_text,
    }
