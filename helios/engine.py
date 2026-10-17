"""Helios diagnostic engine — real Windows 11 readiness, not a costume."""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from helios.cpu import classify_cpu

APP = "Helios"
VERSION = "1.0.0"

PS_INVENTORY = r"""
$ErrorActionPreference = 'SilentlyContinue'
function C($class, $ns = 'root/cimv2') {
  try { Get-CimInstance -Namespace $ns -ClassName $class -OperationTimeoutSec 5 } catch { $null }
}

$os = C 'Win32_OperatingSystem' | Select-Object Caption, Version, BuildNumber, OSArchitecture, LastBootUpTime, CSName
$cpu = C 'Win32_Processor' | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, AddressWidth, Manufacturer, VirtualizationFirmwareEnabled
$cs = C 'Win32_ComputerSystem' | Select-Object Manufacturer, Model, TotalPhysicalMemory, HypervisorPresent
$bios = C 'Win32_BIOS' | Select-Object Manufacturer, SMBIOSBIOSVersion
$board = C 'Win32_BaseBoard' | Select-Object Manufacturer, Product
$disks = @(C 'Win32_DiskDrive' | Select-Object Model, Size, MediaType, InterfaceType)
$logical = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -OperationTimeoutSec 5 | Select-Object DeviceID, Size, FreeSpace, FileSystem)
$gpu = @(C 'Win32_VideoController' | Select-Object Name, DriverVersion, AdapterRAM, CurrentHorizontalResolution, CurrentVerticalResolution, Status, AdapterCompatibility)
$tpm = $null
try { $tpm = Get-CimInstance -Namespace root/cimv2/Security/MicrosoftTpm -ClassName Win32_Tpm -OperationTimeoutSec 4 | Select-Object IsEnabled_InitialValue, IsActivated_InitialValue, SpecVersion, ManufacturerIdTxt } catch {}
$secureBoot = $null
try { $secureBoot = [bool](Confirm-SecureBootUEFI) } catch { $secureBoot = $null }
$firmware = $env:firmware_type
$secureBootReg = $null
try { $secureBootReg = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' -ErrorAction Stop).UEFISecureBootEnabled } catch {}
$dx = $null
try { $dx = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\DirectX' | Select-Object Version } catch {}
$rtDisabled = $null
try { $rtDisabled = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Defender\Real-Time Protection' -ErrorAction Stop).DisableRealtimeMonitoring } catch {}
$defenderSvc = $null
try { $defenderSvc = (Get-Service WinDefend -ErrorAction Stop).Status.ToString() } catch {}
$firewall = @()
try { $firewall = @(Get-NetFirewallProfile -ErrorAction Stop | Select-Object Name, Enabled) } catch {}
$vbs = $null
try { $vbs = Get-CimInstance -Namespace root/Microsoft/Windows/DeviceGuard -ClassName Win32_DeviceGuard -OperationTimeoutSec 4 | Select-Object VirtualizationBasedSecurityStatus, SecurityServicesRunning } catch {}
$license = @()
try { $license = @(Get-CimInstance SoftwareLicensingProduct -OperationTimeoutSec 5 | Where-Object { $_.PartialProductKey -and $_.Name -like '*Windows*' } | Select-Object Name, LicenseStatus, PartialProductKey) } catch {}
$net = @(Get-CimInstance Win32_NetworkAdapter -Filter "NetEnabled=True" -OperationTimeoutSec 5 | Select-Object Name, NetConnectionID)
$bitlocker = @()
try { $bitlocker = @(Get-BitLockerVolume -ErrorAction Stop | Select-Object MountPoint, VolumeStatus, ProtectionStatus) } catch {}

$defender = [ordered]@{
  AntivirusEnabled = ($defenderSvc -eq 'Running')
  RealTimeProtectionEnabled = ($defenderSvc -eq 'Running' -and ($rtDisabled -eq 0 -or $null -eq $rtDisabled))
}

[ordered]@{
  os = $os; cpu = $cpu; cs = $cs; bios = $bios; board = $board
  disks = $disks; logical = $logical; gpu = $gpu; tpm = $tpm
  secureBoot = $secureBoot; firmware = $firmware; secureBootReg = $secureBootReg
  dx = $dx; bitlocker = $bitlocker; defender = $defender; firewall = $firewall
  vbs = $vbs; license = $license; hotfixCount = 0; net = $net; battery = @()
} | ConvertTo-Json -Depth 8 -Compress
"""


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _gb(byte_count: Any) -> float:
    return round(_num(byte_count) / (1024**3), 2)


def _spec_major(spec: str | None) -> float:
    if not spec:
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)", str(spec))
    return float(m.group(1)) if m else 0.0


def _check(
    id_: str,
    title: str,
    category: str,
    status: str,
    summary: str,
    *,
    required: bool = True,
    detail: str = "",
    value: str = "",
    hint: str = "",
    weight: int = 10,
) -> dict[str, Any]:
    return {
        "id": id_,
        "title": title,
        "category": category,
        "status": status,
        "required": required,
        "summary": summary,
        "detail": detail,
        "value": value,
        "hint": hint,
        "weight": weight,
    }


def collect_inventory(timeout: int = 35) -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"_error": "Helios предназначен для Windows."}
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); "
            + PS_INVENTORY,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    raw = (completed.stdout or "").strip()
    if not raw:
        err = (completed.stderr or "").strip()[:400]
        return {"_error": err or "PowerShell не вернул инвентарь."}
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {"_raw_list": data, "_error": "Неожиданный JSON-массив."}
        return data
    except json.JSONDecodeError:
        return {"_error": "Не удалось разобрать инвентарь.", "_preview": raw[:300]}


def evaluate(inv: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    osinfo = _first(inv.get("os")) or {}
    cpu = _first(inv.get("cpu")) or {}
    cs = _first(inv.get("cs")) or {}
    bios = _first(inv.get("bios")) or {}
    board = _first(inv.get("board")) or {}
    tpm = _first(inv.get("tpm")) or {}
    gpus = inv.get("gpu") or []
    if isinstance(gpus, dict):
        gpus = [gpus]
    disks = inv.get("disks") or []
    if isinstance(disks, dict):
        disks = [disks]
    logical = inv.get("logical") or []
    if isinstance(logical, dict):
        logical = [logical]

    caption = str(osinfo.get("Caption") or platform.platform())
    build = int(_num(osinfo.get("BuildNumber")))
    arch = str(osinfo.get("OSArchitecture") or "")
    if build >= 22000:
        checks.append(
            _check(
                "os",
                "Система",
                "identity",
                "pass",
                "Это Windows 11.",
                value=f"{caption} · сборка {build}",
                detail=f"Архитектура {arch or '—'}. Последняя загрузка: {osinfo.get('LastBootUpTime') or '—'}.",
                weight=8,
            )
        )
    elif build >= 10240:
        checks.append(
            _check(
                "os",
                "Система",
                "identity",
                "warn",
                "Сейчас Windows 10 — Helios проверяет, пустит ли вас Windows 11.",
                value=f"{caption} · сборка {build}",
                hint="Если железо проходит, обновление возможно через помощник или чистую установку.",
                weight=8,
            )
        )
    else:
        checks.append(
            _check(
                "os",
                "Система",
                "identity",
                "fail",
                "Сборка слишком старая даже для Windows 10 как базы обновления.",
                value=caption,
                weight=8,
            )
        )

    ram_gb = _gb(cs.get("TotalPhysicalMemory"))
    if ram_gb >= 4:
        checks.append(
            _check(
                "ram",
                "Память",
                "hardware",
                "pass" if ram_gb >= 8 else "warn",
                "Минимум 4 ГБ выполнен."
                if ram_gb >= 8
                else "Формально хватает, но 8 ГБ — разумный пол для Windows 11.",
                value=f"{ram_gb} ГБ",
                weight=10,
            )
        )
    else:
        checks.append(
            _check(
                "ram",
                "Память",
                "hardware",
                "fail",
                "Меньше 4 ГБ — официальный минимум не выполнен.",
                value=f"{ram_gb} ГБ",
                hint="Добавьте планку ОЗУ. 8 ГБ — комфортный минимум, 16 ГБ — норма 2026 года.",
                weight=12,
            )
        )

    total_storage = sum(_num(d.get("Size")) for d in disks) / (1024**3)
    free_storage = sum(_num(d.get("FreeSpace")) for d in logical) / (1024**3)
    if not total_storage:
        total_storage = sum(_num(d.get("Size")) for d in logical) / (1024**3)
    media = ", ".join(
        filter(
            None,
            {
                f"{d.get('Model') or 'диск'} ({d.get('MediaType') or d.get('InterfaceType') or '?'})"
                for d in disks
            },
        )
    )
    if total_storage >= 64:
        st = "pass"
        summary = "Ёмкость накопителя проходит минимум 64 ГБ."
        if free_storage < 20:
            st = "warn"
            summary = "Места на диске мало для установки и обновлений."
    else:
        st = "fail"
        summary = "Меньше 64 ГБ суммарно — Windows 11 не установится штатно."
    checks.append(
        _check(
            "storage",
            "Накопитель",
            "hardware",
            st,
            summary,
            value=f"{total_storage:.0f} ГБ · свободно {free_storage:.0f} ГБ",
            detail=media or "Модель диска недоступна.",
            hint="SSD решительно лучше HDD: установка и обновления не будут пыткой.",
            weight=10,
        )
    )

    cores = int(_num(cpu.get("NumberOfCores")))
    threads = int(_num(cpu.get("NumberOfLogicalProcessors")))
    mhz = int(_num(cpu.get("MaxClockSpeed")))
    width = int(_num(cpu.get("AddressWidth")))
    cpu_name = str(cpu.get("Name") or "").strip()
    verdict = classify_cpu(cpu_name, cores or 0, width or 64)
    if cores >= 2 and mhz >= 1000 and verdict.official:
        cpu_status = "pass"
    elif cores >= 2 and mhz >= 1000 and verdict.confidence == "low":
        cpu_status = "warn"
    elif cores >= 2 and mhz >= 1000 and not verdict.official:
        cpu_status = "fail"
    else:
        cpu_status = "fail"
    checks.append(
        _check(
            "cpu",
            "Процессор",
            "hardware",
            cpu_status,
            verdict.note,
            value=cpu_name or "неизвестно",
            detail=f"{verdict.generation} · {cores} ядер / {threads} потоков · {mhz} МГц · {width}-bit",
            hint="Неофициальные обходы TPM/CPU существуют, но это уже не Helios и не Microsoft.",
            weight=16,
        )
    )

    virt = cpu.get("VirtualizationFirmwareEnabled")
    hv = cs.get("HypervisorPresent")
    if virt or hv:
        checks.append(
            _check(
                "virt",
                "Виртуализация",
                "firmware",
                "pass",
                "Виртуализация в прошивке доступна — Core Isolation / VBS смогут работать.",
                value="Hypervisor" if hv else "firmware enabled",
                required=False,
                weight=4,
            )
        )
    else:
        checks.append(
            _check(
                "virt",
                "Виртуализация",
                "firmware",
                "warn",
                "SVM/VT-x, похоже, выключены. Windows 11 это переживёт, безопасность — нет.",
                hint="В BIOS включите Intel VT-x / AMD-V / SVM Mode.",
                required=False,
                weight=4,
            )
        )

    firmware = str(inv.get("firmware") or "").upper()
    if firmware == "UEFI":
        fw_status, fw_sum = "pass", "Загрузка в режиме UEFI."
    elif firmware == "LEGACY":
        fw_status, fw_sum = "fail", "Legacy BIOS / CSM. Windows 11 требует UEFI."
    else:
        fw_status, fw_sum = "warn", "Тип прошивки не удалось прочитать (часто так в VM)."
    bios_line = " · ".join(
        filter(
            None,
            [
                bios.get("Manufacturer"),
                bios.get("SMBIOSBIOSVersion"),
                board.get("Manufacturer"),
                board.get("Product"),
            ],
        )
    )
    checks.append(
        _check(
            "uefi",
            "UEFI",
            "firmware",
            fw_status,
            fw_sum,
            value=firmware or "неизвестно",
            detail=bios_line,
            hint="Отключите CSM / Legacy Boot в прошивке, диск должен быть GPT.",
            weight=14,
        )
    )

    sb = inv.get("secureBoot")
    sb_reg = inv.get("secureBootReg")
    enabled = sb is True or sb_reg in (1, "1", True)
    if enabled:
        checks.append(
            _check(
                "secureboot",
                "Secure Boot",
                "firmware",
                "pass",
                "Secure Boot включён.",
                value="on",
                weight=14,
            )
        )
    elif sb is False or sb_reg in (0, "0", False):
        checks.append(
            _check(
                "secureboot",
                "Secure Boot",
                "firmware",
                "fail",
                "Secure Boot выключен. Для чистой Windows 11 его нужно уметь включить.",
                value="off",
                hint="UEFI → Boot → Secure Boot = Enabled. Если серый — сначала UEFI+GPT, без CSM.",
                weight=14,
            )
        )
    else:
        checks.append(
            _check(
                "secureboot",
                "Secure Boot",
                "firmware",
                "warn",
                "Не удалось опросить Secure Boot. На Legacy это нормально — он просто не существует.",
                value="n/a",
                weight=10,
            )
        )

    spec = _spec_major(str(tpm.get("SpecVersion") or ""))
    present = bool(tpm) and spec > 0
    tpm_on = bool(tpm.get("IsEnabled_InitialValue")) or present
    if present and spec >= 2.0 and tpm_on:
        checks.append(
            _check(
                "tpm",
                "TPM 2.0",
                "firmware",
                "pass",
                "Модуль TPM 2.0 на месте и включён.",
                value=str(tpm.get("SpecVersion")),
                detail=str(tpm.get("ManufacturerIdTxt") or ""),
                weight=16,
            )
        )
    elif present and spec >= 2.0:
        checks.append(
            _check(
                "tpm",
                "TPM 2.0",
                "firmware",
                "warn",
                "TPM 2.0 найден, но не выглядит включённым.",
                value=str(tpm.get("SpecVersion")),
                hint="BIOS: Intel PTT / AMD fTPM = Enabled. Затем tpm.msc.",
                weight=16,
            )
        )
    elif present:
        checks.append(
            _check(
                "tpm",
                "TPM 2.0",
                "firmware",
                "fail",
                "Есть TPM, но версии 1.2. Windows 11 хочет 2.0.",
                value=str(tpm.get("SpecVersion")),
                hint="Включите fTPM/PTT — часто 1.2 превращается в 2.0 после смены режима.",
                weight=16,
            )
        )
    else:
        checks.append(
            _check(
                "tpm",
                "TPM 2.0",
                "firmware",
                "fail",
                "TPM не виден. Без него официальная установка Windows 11 не пройдёт.",
                value="нет",
                hint="Intel PTT или AMD fTPM в UEFI. На очень старых платах модуля может не быть вовсе.",
                weight=16,
            )
        )

    real_gpus = [
        g
        for g in gpus
        if g and "basic display" not in str(g.get("Name") or "").lower()
    ]
    gpu0 = _first(real_gpus or gpus) or {}
    w = int(_num(gpu0.get("CurrentHorizontalResolution")))
    h = int(_num(gpu0.get("CurrentVerticalResolution")))
    gpu_name = str(gpu0.get("Name") or "нет видеоадаптера")
    dx = _first(inv.get("dx")) or {}
    dx_ver = str(dx.get("Version") or "")
    if real_gpus:
        gstatus = "pass"
        gsum = "Дискретный или чипсетный GPU найден. На Windows 10/11 это почти всегда DirectX 12 + WDDM 2.x."
        if w and h and (w < 1280 or h < 720):
            gstatus = "warn"
            gsum = "GPU есть, но текущий режим меньше 720p."
    else:
        gstatus = "fail"
        gsum = "Только Basic Display Adapter — драйвера видео нет."
    checks.append(
        _check(
            "gpu",
            "Графика",
            "graphics",
            gstatus,
            gsum,
            value=gpu_name,
            detail=f"Драйвер {gpu0.get('DriverVersion') or '—'} · DirectX {dx_ver or '—'} · {w}×{h}"
            if gpu0
            else "",
            hint="Поставьте свежий драйвер NVIDIA / AMD / Intel. WDDM 2.0 — минимум Microsoft.",
            weight=10,
        )
    )

    if w >= 1280 and h >= 720:
        checks.append(
            _check(
                "display",
                "Дисплей",
                "graphics",
                "pass",
                "Разрешение не ниже HD.",
                value=f"{w}×{h}",
                required=False,
                weight=4,
            )
        )
    elif w or h:
        checks.append(
            _check(
                "display",
                "Дисплей",
                "graphics",
                "fail",
                "Нужен 720p (1280×720) и диагональ от 9″.",
                value=f"{w}×{h}",
                required=False,
                weight=4,
            )
        )
    else:
        checks.append(
            _check(
                "display",
                "Дисплей",
                "graphics",
                "skip",
                "Текущий режим монитора недоступен (RDP/VM без GPU).",
                required=False,
                weight=2,
            )
        )

    defender = _first(inv.get("defender")) or {}
    if defender.get("AntivirusEnabled") or defender.get("RealTimeProtectionEnabled"):
        checks.append(
            _check(
                "defender",
                "Антивирус",
                "security",
                "pass",
                "Защитник / сторонний AV активен.",
                value="realtime on"
                if defender.get("RealTimeProtectionEnabled")
                else "AV on",
                required=False,
                weight=3,
            )
        )
    else:
        checks.append(
            _check(
                "defender",
                "Антивирус",
                "security",
                "warn",
                "Реальное время защиты не видно. Это не блокер установки, но дыра.",
                required=False,
                hint="Проверьте «Безопасность Windows» → защита от вирусов.",
                weight=3,
            )
        )

    fw = inv.get("firewall") or []
    if isinstance(fw, dict):
        fw = [fw]
    enabled_profiles = [p.get("Name") for p in fw if p.get("Enabled") in (True, 1, "1")]
    if enabled_profiles:
        checks.append(
            _check(
                "firewall",
                "Брандмауэр",
                "security",
                "pass",
                "Профили брандмауэра включены.",
                value=", ".join(str(x) for x in enabled_profiles),
                required=False,
                weight=2,
            )
        )
    else:
        checks.append(
            _check(
                "firewall",
                "Брандмауэр",
                "security",
                "warn",
                "Все профили брандмауэра выключены или недоступны.",
                required=False,
                weight=2,
            )
        )

    bl = inv.get("bitlocker") or []
    if isinstance(bl, dict):
        bl = [bl]
    protected = [
        b
        for b in bl
        if str(b.get("ProtectionStatus")) in ("1", "On", "on")
        or b.get("ProtectionStatus") in (1, True)
        or str(b.get("VolumeStatus")).lower() == "fullyencrypted"
    ]
    if protected:
        checks.append(
            _check(
                "bitlocker",
                "BitLocker",
                "security",
                "pass",
                "Шифрование тома включено.",
                value=", ".join(str(b.get("MountPoint")) for b in protected),
                required=False,
                weight=3,
            )
        )
    else:
        checks.append(
            _check(
                "bitlocker",
                "BitLocker",
                "security",
                "skip",
                "BitLocker не включён. Для Home это часто норма, для устройства без TPM — ожидаемо.",
                required=False,
                hint="При TPM 2.0 включить шифрование устройства стоит десяти минут.",
                weight=2,
            )
        )

    vbs = _first(inv.get("vbs")) or {}
    vbs_status = vbs.get("VirtualizationBasedSecurityStatus")
    # 0 off, 1 enabled, 2 running
    if vbs_status in (2, "2"):
        checks.append(
            _check(
                "vbs",
                "Memory integrity / VBS",
                "security",
                "pass",
                "Virtualization-based security запущена.",
                required=False,
                weight=3,
            )
        )
    elif vbs_status in (1, "1"):
        checks.append(
            _check(
                "vbs",
                "Memory integrity / VBS",
                "security",
                "warn",
                "VBS включена, но ещё не running.",
                required=False,
                weight=3,
            )
        )
    else:
        checks.append(
            _check(
                "vbs",
                "Memory integrity / VBS",
                "security",
                "skip",
                "VBS выключена. На Windows 11 это уже не блокер установки, но изоляция ядра полезнее включённой.",
                required=False,
                hint="Безопасность Windows → изоляция ядра → целостность памяти.",
                weight=2,
            )
        )

    licenses = inv.get("license") or []
    if isinstance(licenses, dict):
        licenses = [licenses]
    licensed = any(int(_num(x.get("LicenseStatus"))) == 1 for x in licenses)
    if licensed:
        name = next(
            (x.get("Name") for x in licenses if int(_num(x.get("LicenseStatus"))) == 1),
            "Windows",
        )
        checks.append(
            _check(
                "license",
                "Лицензия",
                "identity",
                "pass",
                "Windows активирована.",
                value=str(name),
                required=False,
                weight=3,
            )
        )
    elif licenses:
        checks.append(
            _check(
                "license",
                "Лицензия",
                "identity",
                "warn",
                "Ключ виден, но статус не «licensed».",
                required=False,
                weight=3,
            )
        )
    else:
        checks.append(
            _check(
                "license",
                "Лицензия",
                "identity",
                "skip",
                "Сведения об активации недоступны (нужны права или WMI).",
                required=False,
                weight=1,
            )
        )

    nets = inv.get("net") or []
    if isinstance(nets, dict):
        nets = [nets]
    live = [n for n in nets if n.get("Name")]
    if live:
        checks.append(
            _check(
                "net",
                "Сеть",
                "health",
                "pass",
                f"Активных адаптеров: {len(live)}.",
                value=str(live[0].get("NetConnectionID") or live[0].get("Name")),
                required=False,
                weight=2,
            )
        )
    else:
        checks.append(
            _check(
                "net",
                "Сеть",
                "health",
                "warn",
                "Нет активных сетевых адаптеров. Для Windows 11 Home на OOBE интернет обязателен.",
                required=False,
                weight=2,
            )
        )

    hotfixes = int(_num(inv.get("hotfixCount")))
    checks.append(
        _check(
            "updates",
            "Обновления",
            "health",
            "pass" if hotfixes else "skip",
            f"Установлено исправлений (QuickFix): {hotfixes}."
            if hotfixes
            else "Список hotfix пуст или недоступен — это не приговор.",
            value=str(hotfixes),
            required=False,
            hint="Helios больше не вызывает Get-WindowsUpdateLog: он вешал старый чекер на минуты.",
            weight=2,
        )
    )
    return checks


def score_of(checks: list[dict[str, Any]]) -> dict[str, Any]:
    weights = {"pass": 1.0, "warn": 0.45, "skip": 0.7, "fail": 0.0}
    required = [c for c in checks if c.get("required")]
    pool = required or checks
    total_w = sum(int(c.get("weight") or 10) for c in pool) or 1
    gained = sum(int(c.get("weight") or 10) * weights.get(c["status"], 0) for c in pool)
    value = int(round(100 * gained / total_w))
    blocking = [c for c in required if c["status"] == "fail"]
    if blocking:
        label = "Не готов"
        ready = False
        tone = "fail"
        if value > 35:
            label = "Почти, но нет"
    elif any(c["status"] == "warn" for c in required):
        label = "С оговорками"
        ready = True
        tone = "warn"
    else:
        label = "Готов к Windows 11"
        ready = True
        tone = "pass"
        if value >= 95:
            label = "Сияет"
    return {
        "value": value,
        "label": label,
        "ready": ready,
        "tone": tone,
        "blocking": [c["id"] for c in blocking],
    }


def run_scan() -> dict[str, Any]:
    t0 = time.perf_counter()
    inv = collect_inventory()
    if inv.get("_error") and not inv.get("os"):
        checks = [
            _check(
                "engine",
                "Движок",
                "health",
                "fail",
                inv.get("_error") or "Скан сорвался.",
                hint="Запустите Helios от имени пользователя Windows. Часть WMI-классов молчит в песочнице.",
            )
        ]
    else:
        checks = evaluate(inv)
    score = score_of(checks)
    osinfo = _first(inv.get("os")) or {}
    cpu = _first(inv.get("cpu")) or {}
    cs = _first(inv.get("cs")) or {}
    elapsed = int((time.perf_counter() - t0) * 1000)
    return {
        "meta": {
            "app": APP,
            "version": VERSION,
            "scannedAt": datetime.now(timezone.utc).isoformat(),
            "elapsedMs": elapsed,
            "hostname": osinfo.get("CSName") or socket.gethostname(),
            "user": os.environ.get("USERNAME") or "",
        },
        "identity": {
            "os": osinfo.get("Caption") or platform.platform(),
            "build": osinfo.get("BuildNumber"),
            "arch": osinfo.get("OSArchitecture"),
            "cpu": (cpu.get("Name") or "").strip(),
            "machine": " ".join(
                filter(None, [cs.get("Manufacturer"), cs.get("Model")])
            ),
        },
        "score": score,
        "checks": checks,
        "inventory": {
            "firmware": inv.get("firmware"),
            "hotfixCount": inv.get("hotfixCount"),
            "error": inv.get("_error"),
        },
    }
