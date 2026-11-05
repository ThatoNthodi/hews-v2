"""The agent team. Each agent has one job, a narrow prompt, and a deterministic fallback.
Safety-critical paths (risk tiers, emergency messages) never depend on the AI."""
from typing import List
from . import messages as M
from .risk import NAMES, final_tier
from .schemas import Crew, Reading, RiskResult, SymptomReport

FORBIDDEN_IN_SUPERVISOR_VIEW = ("heart rate", "heart-rate", "skin temp", "personal strain", "symptom history", "diagnos")


class Assessor:
    """Risk Assessor: reviews the engine's result and may only make it MORE cautious."""
    name = "assessor"
    SYSTEM = ("You are the Risk Assessor in a workplace heat-safety team. A deterministic engine has already "
              "computed an alert tier (0 Green, 1 Yellow, 2 Orange, 3 Red). You may suggest the same or a HIGHER tier "
              "only if the context clearly warrants it (for example a rapidly rising forecast, or an unusually risky "
              "combination of task, PPE and acclimatisation). Never suggest a lower tier. "
              'Reply with JSON only: {"suggested_tier": 0-3, "rationale": "max 40 words", "watch_items": ["short item"]}.')

    def __init__(self, llm):
        self.llm = llm

    def run(self, crew: Crew, reading: Reading, engine: RiskResult) -> dict:
        user = (f"Crew: {crew.size} workers, {crew.task} task, PPE {crew.ppe}, acclimatised={crew.acclimatised}. "
                f"Reading at {reading.time}: wbgt={reading.wbgt}, forecast_2h={reading.forecast_2h}, "
                f"network_up={reading.network_up}, sensor_ok={reading.sensor_ok}. "
                f"Engine: tier {engine.tier} ({engine.name}), margin={engine.margin}, forecast_margin={engine.forecast_margin}. "
                f"Reason: {engine.reason}")
        out = self.llm.json(self.SYSTEM, user)
        suggested = out.get("suggested_tier") if out else None
        tier = final_tier(engine.tier, suggested)
        return {"engine_tier": engine.tier, "ai_suggested": suggested, "tier": tier, "name": NAMES[tier],
                "raised_by_ai": tier > engine.tier,
                "rationale": (out or {}).get("rationale") or engine.reason,
                "watch_items": (out or {}).get("watch_items") or [],
                "source": "ai+engine" if out else "engine"}


class Comms:
    """Communications: vetted templates first; AI only drafts languages we have no vetted text for."""
    name = "comms"
    SYSTEM = ("You translate short workplace heat-safety alerts for South African workers. Keep the meaning exactly, "
              "keep any emergency numbers (112, 10177) unchanged, use plain everyday words, maximum 200 characters. "
              'Reply with JSON only: {"text": "..."}.')

    def __init__(self, llm):
        self.llm = llm

    def run(self, tier: int, crew: Crew) -> dict:
        out = {}
        for lang in crew.languages:
            vetted = M.template(tier, lang)
            if vetted:
                out[lang] = {"text": vetted, "source": "vetted-template", "needs_review": False}
                continue
            english = M.template(tier, "en")
            drafted = None
            if tier < 4:   # emergency wording is never AI-drafted
                res = self.llm.json(self.SYSTEM + f" Target language: {M.LANG_NAMES.get(lang, lang)}.", f"Translate: {english}", 300)
                drafted = (res or {}).get("text")
            ok = False
            if drafted:
                ok, _ = M.validate(drafted, tier)
            if ok:
                out[lang] = {"text": drafted, "source": "ai-draft", "needs_review": True}
            else:
                out[lang] = {"text": english, "source": "english-fallback", "needs_review": True}
        return out


class SupervisorAdvisor:
    """Supervisor Advisor: crew-level plan only. It never receives individual data."""
    name = "supervisor_advisor"
    SYSTEM = ("You advise a site supervisor on heat safety. You only know crew-level information, never individuals. "
              "Give practical, specific advice. "
              'Reply with JSON only: {"summary": "max 25 words", "work_rest": "short", "rotation": "short", "outlook": "max 20 words"}.')

    def __init__(self, llm):
        self.llm = llm

    def run(self, crew: Crew, reading: Reading, risk: RiskResult, tier: int) -> dict:
        outlook = ("Forecast unavailable (network down); margins widened." if (reading.forecast_2h is None or not reading.network_up)
                   else ("Likely Red in 2 hours" if (risk.forecast_margin or -9) >= 2 else "Likely Orange in 2 hours" if (risk.forecast_margin or -9) >= 0
                         else "Likely Yellow in 2 hours" if (risk.forecast_margin or -9) >= -3 else "Likely Green in 2 hours"))
        base = {"summary": f"{NAMES[tier]} at {crew.zone}. {M.ACTION[tier]}", "work_rest": M.WORK_REST[tier],
                "rotation": "Rotate heavy tasks to cooler hours and shaded work." if tier >= 2 else "No rotation needed.",
                "outlook": outlook, "source": "engine"}
        user = (f"Zone {crew.zone}: crew of {crew.size}, {crew.task} task, PPE {crew.ppe}, acclimatised={crew.acclimatised}. "
                f"Alert tier {NAMES[tier]}. {risk.reason} Outlook: {outlook}")
        out = self.llm.json(self.SYSTEM, user, 500)
        if out and all(isinstance(out.get(k), str) for k in ("summary", "work_rest", "rotation", "outlook")):
            text = " ".join(out[k] for k in ("summary", "work_rest", "rotation", "outlook")).lower()
            if not any(f in text for f in FORBIDDEN_IN_SUPERVISOR_VIEW):
                base = {k: out[k] for k in ("summary", "work_rest", "rotation", "outlook")}
                base["source"] = "ai"
        return base


class Escalation:
    """Escalation: deterministic emergency protocol. The AI is deliberately NOT on this path."""
    name = "escalation"

    def run(self, crew: Crew, report: SymptomReport) -> dict:
        return {"tier": 4, "name": "Emergency",
                "steps": ["Move the worker to shade and start cooling now.", "Call 112 or 10177.",
                          "Alert the site first-aider with the zone and crew.", "Do not leave the worker alone."],
                "first_aider_message": f"HEAT EMERGENCY at {crew.zone} (crew {crew.crew_id}, {report.time}). Red-flag symptoms reported. Go now.",
                "source": "protocol"}


class Auditor:
    """Governance Auditor: checks every outgoing payload and produces de-identified reports."""
    name = "auditor"

    def check(self, worker_msgs: dict, supervisor_view: dict) -> List[str]:
        problems = []
        for lang, m in worker_msgs.items():
            ok, p = M.validate(m["text"], m.get("tier", 0))
            problems += [f"worker message [{lang}]: {x}" for x in p]
        blob = " ".join(str(v) for v in supervisor_view.values()).lower()
        problems += [f"supervisor view mentions '{f}'" for f in FORBIDDEN_IN_SUPERVISOR_VIEW if f in blob]
        if M.PHONE.search(blob):
            problems.append("supervisor view contains a phone-number-like string")
        return problems

    def report(self, history: list) -> dict:
        tiers = [h["tier"] for h in history]
        return {"cycles": len(history),
                "by_tier": {NAMES[t]: tiers.count(t) for t in range(5)},
                "raised_by_ai": sum(1 for h in history if h.get("raised_by_ai")),
                "fallback_protocol_uses": sum(1 for h in history if h.get("fallback")),
                "emergencies": tiers.count(4),
                "individual_health_data_stored": False}
