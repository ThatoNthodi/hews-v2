"""The Orchestrator: runs the agent team for each event and enforces the rules."""
from typing import Dict, List
from . import messages as M
from .agents import Assessor, Auditor, Comms, Escalation, SupervisorAdvisor
from .audit import AuditLog
from .llm import LLM
from .risk import NAMES, assess
from .schemas import Crew, Reading, SymptomReport


class Outbox:
    """Dry-run outbox. Live WhatsApp/SMS sending is a later step."""
    def __init__(self):
        self.sent: List[dict] = []

    def send(self, channel: str, to: str, text: str):
        self.sent.append({"channel": channel, "to": to, "text": text})


class Team:
    def __init__(self, llm: LLM = None, audit_path: str = "audit.jsonl"):
        self.llm = llm or LLM(enabled=False)
        self.audit = AuditLog(audit_path)
        self.outbox = Outbox()
        self.assessor, self.comms = Assessor(self.llm), Comms(self.llm)
        self.advisor, self.escalation, self.auditor = SupervisorAdvisor(self.llm), Escalation(), Auditor()
        self.last_tier: Dict[str, int] = {}
        self.history: List[dict] = []

    def on_reading(self, crew: Crew, reading: Reading) -> dict:
        engine = assess(crew, reading)
        self.audit.write("engine", "risk", {"crew": crew.crew_id, "time": reading.time, "tier": engine.tier, "reason": engine.reason})
        a = self.assessor.run(crew, reading, engine)
        self.audit.write("assessor", "review", {"crew": crew.crew_id, "engine_tier": a["engine_tier"], "ai_suggested": a["ai_suggested"], "final": a["tier"], "source": a["source"]})
        tier = a["tier"]

        msgs = self.comms.run(tier, crew)
        for m in msgs.values():
            m["tier"] = tier
        view = self.advisor.run(crew, reading, engine, tier)
        view["tier"] = NAMES[tier]
        problems = self.auditor.check(msgs, view)
        if problems:       # fall back to vetted English and the plain engine view
            self.audit.write("auditor", "blocked", {"crew": crew.crew_id, "problems": problems})
            msgs = {l: {"text": M.template(tier, "en"), "source": "safety-fallback", "needs_review": True, "tier": tier} for l in crew.languages}
            view = {"summary": f"{NAMES[tier]} at {crew.zone}. {M.ACTION[tier]}", "work_rest": M.WORK_REST[tier], "rotation": "", "outlook": "", "tier": NAMES[tier], "source": "engine"}

        prev = self.last_tier.get(crew.crew_id)
        sent = []
        if prev is None or tier != prev:       # one alert per tier change (alert hygiene)
            for l, m in msgs.items():
                self.outbox.send("whatsapp", f"crew:{crew.crew_id}:{l}", m["text"])
                sent.append(l)
        self.outbox.send("dashboard", f"supervisor:{crew.zone}", f"{view['summary']} Plan: {view['work_rest']}. Outlook: {view['outlook']}")
        self.last_tier[crew.crew_id] = tier
        self.audit.write("comms", "sent" if sent else "suppressed-repeat", {"crew": crew.crew_id, "tier": tier, "languages": sent, "sources": {l: m["source"] for l, m in msgs.items()}})
        rec = {"crew": crew.crew_id, "time": reading.time, "tier": tier, "name": NAMES[tier], "reason": a["rationale"],
               "raised_by_ai": a["raised_by_ai"], "fallback": engine.fallback_protocol, "messages": msgs, "supervisor": view, "alert_sent": bool(sent)}
        self.history.append(rec)
        return rec

    def on_symptom(self, crew: Crew, report: SymptomReport) -> dict:
        e = self.escalation.run(crew, report)
        crew_em = Crew(crew.crew_id, crew.zone, crew.size, crew.task, crew.ppe, crew.acclimatised, crew.languages)
        msgs = self.comms.run(4, crew_em)      # templates only for Emergency
        for l, m in msgs.items():
            self.outbox.send("whatsapp", f"crew:{crew.crew_id}:{l}", m["text"])
        self.outbox.send("whatsapp", f"first-aider:{crew.zone}", e["first_aider_message"])
        self.outbox.send("dashboard", f"supervisor:{crew.zone}", f"Emergency at {crew.zone}. First-aider alerted.")
        self.last_tier[crew.crew_id] = 4
        self.audit.write("escalation", "emergency", {"crew": crew.crew_id, "zone": crew.zone, "time": report.time})
        rec = {"crew": crew.crew_id, "time": report.time, "tier": 4, "name": "Emergency", "reason": "Red-flag symptoms reported.",
               "raised_by_ai": False, "fallback": False, "messages": msgs, "supervisor": {"summary": "Emergency", "tier": "Emergency"}, "alert_sent": True, "steps": e["steps"]}
        self.history.append(rec)
        return rec

    def daily_report(self) -> dict:
        r = self.auditor.report(self.history)
        self.audit.write("auditor", "daily_report", r)
        return r
