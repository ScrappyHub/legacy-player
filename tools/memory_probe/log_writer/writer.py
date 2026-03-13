import json
import os
from datetime import datetime, UTC


class LogWriter:
    def __init__(self, run_id):
        self.run_id = run_id
        os.makedirs("tools/memory_probe/exports", exist_ok=True)
        self.path = f"tools/memory_probe/exports/{run_id}.ndjson"

    def emit(self, event):
        if "ts" not in event:
            event["ts"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        event["run_id"] = self.run_id

        line = json.dumps(event, separators=(",", ":"))

        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")

        print(line, flush=True)