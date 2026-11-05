"""Append-only, hash-chained audit log. Every agent decision is recorded."""
import hashlib, json, os, time


class AuditLog:
    def __init__(self, path: str):
        self.path = path
        self.prev = "0" * 64
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                if line.strip():
                    self.prev = json.loads(line)["hash"]

    def write(self, agent: str, action: str, data: dict) -> dict:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "agent": agent, "action": action, "data": data, "prev": self.prev}
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.prev = rec["hash"]
        return rec

    @staticmethod
    def verify(path: str) -> bool:
        prev = "0" * 64
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            rec = json.loads(line)
            h = rec.pop("hash")
            if rec["prev"] != prev:
                return False
            if hashlib.sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest() != h:
                return False
            prev = h
        return True
