import psutil


def find_dolphin_process():

    for proc in psutil.process_iter(["pid", "name"]):

        try:

            name = proc.info["name"]

            if not name:
                continue

            name = name.lower()

            if "dolphin" in name:
                return proc

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return None