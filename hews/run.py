"""Run the simulated day:  python -m hews.run --offline"""
import argparse, os
from .audit import AuditLog
from .llm import LLM
from .sim import events
from .team import Team


def main():
    ap = argparse.ArgumentParser(description="Zanti HEWS v2 agent team: simulated day")
    ap.add_argument("--offline", action="store_true", help="do not call the AI; use deterministic fallbacks only")
    ap.add_argument("--out", default="out", help="output folder")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "audit.jsonl")
    if os.path.exists(path):
        os.remove(path)
    llm = LLM(enabled=not args.offline)
    team = Team(llm, path)
    print(f"Mode: {'AI agents (' + llm.provider + ': ' + llm.model + ')' if llm.available else 'offline (deterministic fallbacks)'}\n")
    for kind, crew, obj in events():
        rec = team.on_reading(crew, obj) if kind == "reading" else team.on_symptom(crew, obj)
        flag = " [AI raised tier]" if rec.get("raised_by_ai") else ""
        print(f"{rec['time']}  Crew {rec['crew']}  {rec['name'].upper():9}{flag}  {rec['reason']}")
        if rec.get("alert_sent"):
            for lang, m in rec["messages"].items():
                note = "  (needs review)" if m.get("needs_review") else ""
                print(f"           -> worker [{lang}] {m['text']}{note}")
        print(f"           -> supervisor: {rec['supervisor'].get('work_rest', rec['supervisor'].get('summary'))}")
    rep = team.daily_report()
    print("\nDe-identified daily report:", rep)
    print("Audit log intact:", AuditLog.verify(path), f"({path})")


if __name__ == "__main__":
    main()
