"""What this computer is made of, for the doctor's office. Read locally with the system's own tools; nothing is sent anywhere."""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys

_PS = ("$o=@{cpu=@(Get-CimInstance Win32_Processor|Select-Object Name,NumberOfCores,NumberOfLogicalProcessors);"
       "gpu=@(Get-CimInstance Win32_VideoController|Select-Object Name,DriverVersion);"
       "ram=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;os=(Get-CimInstance Win32_OperatingSystem).Caption};"
       "$o|ConvertTo-Json -Depth 3 -Compress")


def _run(cmd: list[str], timeout: int = 15) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=flags).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\((R|TM|tm|r)\)", "", name or "")).strip()


def parse_windows(text: str) -> dict:
    data = json.loads(text)
    cpus = data.get("cpu") or []
    if isinstance(cpus, dict):
        cpus = [cpus]
    gpus = data.get("gpu") or []
    if isinstance(gpus, dict):
        gpus = [gpus]
    return {"os": _clean(data.get("os") or "Windows"), "cpu": _clean(cpus[0]["Name"]) if cpus else "",
            "cores": sum(int(c.get("NumberOfCores") or 0) for c in cpus) or None,
            "threads": sum(int(c.get("NumberOfLogicalProcessors") or 0) for c in cpus) or None,
            "ram_gb": round(int(data["ram"]) / 1073741824, 1) if data.get("ram") else None,
            "gpus": [{"name": _clean(g.get("Name", ""))} for g in gpus if g.get("Name")]}


def _linux() -> dict:
    cpu = ""
    try:
        for line in open("/proc/cpuinfo", encoding="utf-8", errors="ignore"):
            if line.lower().startswith("model name"):
                cpu = _clean(line.split(":", 1)[1])
                break
    except OSError:
        pass
    ram = None
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            if line.startswith("MemTotal"):
                ram = round(int(line.split()[1]) / 1048576, 1)
                break
    except OSError:
        pass
    gpus = []
    for line in _run(["lspci"]).splitlines():
        if re.search(r"VGA|3D controller|Display controller", line):
            gpus.append({"name": _clean(line.split(":", 2)[-1])})
    return {"os": platform.platform(terse=True), "cpu": cpu, "cores": None, "threads": os.cpu_count(), "ram_gb": ram, "gpus": gpus}


def _mac() -> dict:
    cpu = _clean(_run(["sysctl", "-n", "machdep.cpu.brand_string"]))
    ram = _run(["sysctl", "-n", "hw.memsize"]).strip()
    gpus = [{"name": _clean(m)} for m in re.findall(r"Chipset Model:\s*(.+)", _run(["system_profiler", "SPDisplaysDataType"]))]
    return {"os": "macOS " + platform.mac_ver()[0], "cpu": cpu, "cores": None, "threads": os.cpu_count(),
            "ram_gb": round(int(ram) / 1073741824, 1) if ram.isdigit() else None, "gpus": gpus}


def collect() -> dict:
    info: dict = {}
    try:
        if sys.platform.startswith("win"):
            out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS], 25)
            info = parse_windows(out) if out.strip() else {}
        elif sys.platform == "darwin":
            info = _mac()
        else:
            info = _linux()
    except (ValueError, KeyError, TypeError):
        info = {}
    info.setdefault("os", platform.platform(terse=True))
    info.setdefault("cpu", platform.processor() or "")
    info.setdefault("threads", os.cpu_count())
    info.setdefault("cores", None)
    info.setdefault("ram_gb", None)
    info.setdefault("gpus", [])
    info["arch"] = platform.machine()
    info["verdicts"] = verdicts(info)
    return info


def verdicts(info: dict) -> list[dict]:
    """A rough, honest guide to which families of consoles this computer should handle. Not a benchmark."""
    ram, threads = info.get("ram_gb"), info.get("threads") or 0
    gpu = " ".join(g["name"] for g in info.get("gpus", [])).lower()
    integrated = bool(gpu) and not re.search(r"nvidia|geforce|rtx|gtx|radeon rx|radeon pro|arc a|arc b", gpu)
    ok = bool(ram and ram >= 8 and threads >= 4)
    strong = bool(ram and ram >= 16 and threads >= 8 and not integrated)
    return [{"label": "Classic and handhelds", "consoles": "Atari, NES, SNES, Genesis, Game Boy, GBA, PS1", "level": "great"},
            {"label": "Mid generation", "consoles": "N64, DS, PSP, GameCube, Wii, PS2", "level": "great" if ok else "maybe"},
            {"label": "Heavy", "consoles": "3DS, Xbox, Xbox 360, PS3", "level": "great" if strong else ("maybe" if ok else "tough")}]
