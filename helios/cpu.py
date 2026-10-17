"""Heuristic Windows 11 CPU compatibility (official Microsoft lists, simplified)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CpuVerdict:
    generation: str
    official: bool
    confidence: str  # high | medium | low
    note: str


_INTEL_CORE = re.compile(
    r"\bi([3579])-(\d{4,5})[A-Z]*\b",
    re.IGNORECASE,
)
_INTEL_ULTRA = re.compile(
    r"core\s+ultra\s+\d+\s+(\d{3})\w*",
    re.IGNORECASE,
)
_RYZEN = re.compile(
    r"ryzen\s+(?:ai\s+)?(?:[3579]|threadripper)?\s*(\d{4})",
    re.IGNORECASE,
)
_EPYC = re.compile(r"epyc\s+(\d{4})", re.IGNORECASE)
_XEON = re.compile(r"xeon", re.IGNORECASE)


def classify_cpu(name: str, cores: int, address_width: int) -> CpuVerdict:
    n = name or ""
    if address_width and address_width < 64:
        return CpuVerdict("32-bit", False, "high", "Windows 11 требует 64-бит процессор.")
    if cores < 2:
        return CpuVerdict("1 ядро", False, "high", "Нужно минимум 2 ядра.")

    ultra = _INTEL_ULTRA.search(n)
    if ultra:
        series = int(ultra.group(1)[0])
        return CpuVerdict(
            f"Intel Core Ultra ({series}xx)",
            True,
            "high",
            "Семейство Core Ultra официально поддерживается Windows 11.",
        )

    intel = _INTEL_CORE.search(n)
    if intel:
        digits = intel.group(2)
        gen = int(digits[:2]) if len(digits) == 5 else int(digits[0])
        if gen >= 8:
            return CpuVerdict(
                f"Intel {gen}-е поколение",
                True,
                "high",
                "Intel 8-го поколения и новее — в официальном списке Microsoft.",
            )
        if gen == 7:
            return CpuVerdict(
                "Intel 7-е поколение",
                False,
                "medium",
                "Официально почти не поддерживается (исключения вроде 7820HQ). Чистая установка может быть заблокирована.",
            )
        return CpuVerdict(
            f"Intel {gen}-е поколение",
            False,
            "high",
            "Слишком старое поколение для официальной Windows 11.",
        )

    if _XEON.search(n):
        return CpuVerdict(
            "Intel Xeon",
            True,
            "low",
            "Многие Xeon Coffee Lake и новее поддерживаются, но список точечный. Сверьтесь с каталогом Microsoft.",
        )

    ryzen = _RYZEN.search(n)
    if ryzen:
        model = int(ryzen.group(1))
        family = model // 1000
        is_g = bool(re.search(r"\d{4}G", n, re.I))
        if "ai" in n.lower() or family >= 7:
            return CpuVerdict(
                f"AMD Ryzen {family}000",
                True,
                "high",
                "Zen 3 и новее / Ryzen AI официально поддерживаются.",
            )
        if family >= 5:
            return CpuVerdict(
                f"AMD Ryzen {family}000",
                True,
                "high",
                "Ryzen 5000 (Zen 3) и новее — в официальном списке.",
            )
        if family == 4:
            return CpuVerdict(
                "AMD Ryzen 4000",
                True,
                "medium",
                "Мобильные Renoir (4000) поддерживаются. Настольные 4000G — тоже Zen 2.",
            )
        if family == 3:
            if is_g and model < 4000:
                return CpuVerdict(
                    "AMD Picasso APU",
                    False,
                    "medium",
                    "3200G/3400G (Zen+) официально не поддерживаются. 3600/3700 и т.п. — да.",
                )
            return CpuVerdict(
                "AMD Ryzen 3000 (Zen 2)",
                True,
                "high",
                "Настольные Ryzen 3000 без G — первая официальная линейка AMD для Windows 11.",
            )
        return CpuVerdict(
            f"AMD Ryzen {family}000",
            False,
            "high",
            "Zen / Zen+ первого поколения официально не поддерживаются.",
        )

    epyc = _EPYC.search(n)
    if epyc:
        fam = int(epyc.group(1)[0])
        return CpuVerdict(
            f"AMD EPYC {fam}xxx",
            fam >= 7,
            "medium",
            "Официально: EPYC 2-го поколения (Rome, 7xx2) и новее.",
        )

    if re.search(r"snapdragon|qualcomm", n, re.I):
        return CpuVerdict(
            "Qualcomm",
            True,
            "low",
            "Большинство современных Snapdragon для ПК поддерживаются, но список точечный.",
        )

    return CpuVerdict(
        "не распознан",
        cores >= 2 and (not address_width or address_width >= 64),
        "low",
        "Не удалось сопоставить с каталогом Microsoft. Решение по ядрам и разрядности — ориентир, не приговор.",
    )
