import psutil


SUPPORTED_PROCESS_NAMES = {
    "dolphin.exe",
    "dolphinqt2.exe",
}


class DolphinProcessError(RuntimeError):
    pass


def list_dolphin_processes():
    matches = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info["name"] or "").lower()
            if not name:
                continue
            if name in SUPPORTED_PROCESS_NAMES:
                matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(matches, key=lambda proc: proc.pid)


def find_dolphin_process(pid=None):
    matches = list_dolphin_processes()
    if pid is not None:
        selected = [proc for proc in matches if proc.pid == int(pid)]
        if not selected:
            raise DolphinProcessError(f"DOLPHIN_PID_NOT_FOUND: {pid}")
        return selected[0]
    if not matches:
        return None
    if len(matches) > 1:
        pids = ", ".join(str(proc.pid) for proc in matches)
        raise DolphinProcessError(f"MULTIPLE_DOLPHIN_PROCESSES: {pids}; select a pid explicitly")
    return matches[0]
