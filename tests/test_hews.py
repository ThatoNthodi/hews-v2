import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hews.audit import AuditLog
from hews.llm import LLM
from hews.risk import assess, final_tier
from hews.schemas import Crew, Reading, SymptomReport
from hews.sim import events
from hews.team import Team
from hews import messages as M


class _Block:  # minimal stand-in for the Claude response
    def __init__(self, text): self.text = text
class _Resp:
    def __init__(self, text): self.content = [_Block(text)]
class FakeClient:
    def __init__(self, reply): self.reply = reply; self.messages = self; self.calls = 0
    def create(self, **kw):
        self.calls += 1
        r = self.reply(kw) if callable(self.reply) else self.reply
        return _Resp(r)

def crew(**k):
    d = dict(crew_id="X", zone="Z", size=5, task="moderate", ppe="std", acclimatised=True, languages=["en"])
    d.update(k); return Crew(**d)

def tmp(): return os.path.join(tempfile.mkdtemp(), "audit.jsonl")


def test_engine_tiers_match_demo():
    c = crew(task="heavy", ppe="full", acclimatised=False)
    assert assess(c, Reading("Z", "9", 24.0)).tier == 3          # 24+3-24 = +3 -> Red
    assert assess(crew(), Reading("Z", "9", 20.0, 22.0)).tier == 0
    assert assess(crew(), Reading("Z", "9", 26.0)).tier == 1      # margin -2
    assert assess(crew(), Reading("Z", "9", 28.0)).tier == 2      # margin 0
    assert assess(crew(), Reading("Z", "9", 20.0, 29.0)).tier == 1  # forecast crosses the limit


def test_offline_and_failures_are_more_cautious():
    c = crew()
    base = assess(c, Reading("Z", "9", 25.5)).margin
    assert assess(c, Reading("Z", "9", 25.5, sensor_ok=False)).margin == base + 1.5
    r = assess(c, Reading("Z", "9", None))
    assert r.fallback_protocol and r.tier >= 2


def test_guardrail_ai_can_only_raise():
    assert final_tier(2, 0) == 2
    assert final_tier(1, 3) == 3
    assert final_tier(3, 4) == 3            # the AI can never declare an Emergency
    assert final_tier(0, None, red_flag=True) == 4


def test_ai_cannot_lower_but_can_raise():
    c, r = crew(), Reading("Z", "9", 28.5)   # engine: Orange
    t = Team(LLM(client=FakeClient(json.dumps({"suggested_tier": 0, "rationale": "fine"}))), tmp())
    assert t.on_reading(c, r)["tier"] == 2
    t = Team(LLM(client=FakeClient(json.dumps({"suggested_tier": 3, "rationale": "forecast spiking"}))), tmp())
    rec = t.on_reading(c, r)
    assert rec["tier"] == 3 and rec["raised_by_ai"]


def test_broken_ai_output_falls_back():
    t = Team(LLM(client=FakeClient("not json at all")), tmp())
    rec = t.on_reading(crew(), Reading("Z", "9", 28.5))
    assert rec["tier"] == 2


def test_comms_vetted_first_and_ai_only_for_missing_languages():
    c = crew(languages=["en", "zu", "nso"])
    fake = FakeClient(json.dumps({"text": "Stop work. Move to shade and rest."}))
    t = Team(LLM(client=fake), tmp())
    msgs = t.comms.run(3, c)
    assert msgs["en"]["source"] == "vetted-template" and msgs["zu"]["source"] == "vetted-template"
    assert msgs["nso"]["source"] == "ai-draft" and msgs["nso"]["needs_review"]


def test_bad_ai_translation_is_rejected():
    c = crew(languages=["nso"])
    t = Team(LLM(client=FakeClient(json.dumps({"text": "Call 0821234567 now"}))), tmp())
    m = t.comms.run(2, c)["nso"]
    assert m["source"] == "english-fallback" and m["needs_review"]


def test_emergency_never_uses_ai():
    fake = FakeClient(json.dumps({"text": "x"}))
    t = Team(LLM(client=fake), tmp())
    t.on_symptom(crew(languages=["en", "nso"]), SymptomReport("X", "12:30"))
    assert fake.calls == 0
    texts = [o["text"] for o in t.outbox.sent if o["channel"] == "whatsapp"]
    assert any("112" in x for x in texts)


def test_supervisor_view_blocks_individual_data():
    bad = json.dumps({"summary": "Worker heart rate is high", "work_rest": "x", "rotation": "y", "outlook": "z"})
    t = Team(LLM(client=FakeClient(bad)), tmp())
    view = t.advisor.run(crew(), Reading("Z", "9", 28.5), assess(crew(), Reading("Z", "9", 28.5)), 2)
    assert view["source"] == "engine" and "heart" not in json.dumps(view).lower()


def test_alert_hygiene_one_alert_per_tier_change():
    t = Team(LLM(enabled=False), tmp())
    c = crew()
    first = t.on_reading(c, Reading("Z", "9", 28.5))
    second = t.on_reading(c, Reading("Z", "10", 28.6))
    assert first["alert_sent"] and not second["alert_sent"]


def test_audit_chain_detects_tampering():
    p = tmp(); t = Team(LLM(enabled=False), p)
    t.on_reading(crew(), Reading("Z", "9", 28.5))
    assert AuditLog.verify(p)
    lines = open(p, encoding="utf-8").read().splitlines()
    rec = json.loads(lines[0]); rec["data"]["tier"] = 0
    lines[0] = json.dumps(rec)
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    assert not AuditLog.verify(p)


def test_full_simulated_day_offline():
    t = Team(LLM(enabled=False), tmp())
    for kind, c, obj in events():
        t.on_reading(c, obj) if kind == "reading" else t.on_symptom(c, obj)
    rep = t.daily_report()
    assert rep["emergencies"] == 1 and rep["fallback_protocol_uses"] >= 1
    assert rep["individual_health_data_stored"] is False


def test_ollama_adapter_parses_local_model_reply():
    import io
    from unittest import mock
    from hews.llm import OllamaClient

    class FakeHTTP(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    body = json.dumps({"message": {"content": json.dumps({"suggested_tier": 3, "rationale": "spiking"})}}).encode()
    with mock.patch("urllib.request.urlopen", return_value=FakeHTTP(body)):
        llm = LLM(client=OllamaClient("http://localhost:11434", "qwen3:8b"))
        out = llm.json("sys", "user")
    assert out["suggested_tier"] == 3


def test_ollama_down_means_offline_fallback():
    import os as _os
    from unittest import mock
    with mock.patch.dict(_os.environ, {"HEWS_PROVIDER": "ollama", "OLLAMA_HOST": "http://localhost:9"}):
        assert not LLM().available
