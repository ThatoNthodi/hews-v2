import json
from pathlib import Path

import pandas as pd
import streamlit as st

TIERS = ["Green", "Yellow", "Orange", "Red", "Emergency"]

st.set_page_config(page_title="Zanti HEWS v2", layout="wide")
st.title("Zanti HEWS v2: Heat Early Warning System")
st.caption("Crew-level decisions from the audit log. No individual health data is stored.")


def tier_name(t):
    return TIERS[t] if isinstance(t, int) and 0 <= t < len(TIERS) else str(t)


def load(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def chain_linked(rows):
    return all(b.get("prev") == a.get("hash") for a, b in zip(rows, rows[1:]))


sources = [p for p in ["out/audit.jsonl", "docs/sample_audit.jsonl"] if Path(p).exists()]
if not sources:
    st.error("No audit log found. Run: python -m hews.run")
    st.stop()
path = st.sidebar.selectbox("Audit log", sources)
if st.sidebar.button("Reload"):
    st.rerun()

rows = load(path)

last_engine, decisions, comms, emergencies = {}, [], [], 0
for r in rows:
    agent, action, d = r.get("agent"), r.get("action"), r.get("data", {})
    if agent == "engine" and action == "risk":
        last_engine[d.get("crew")] = d
    elif agent == "assessor" and action == "review":
        e = last_engine.get(d.get("crew"), {})
        decisions.append({
            "Time": e.get("time", "?"),
            "Crew": d.get("crew"),
            "Engine tier": d.get("engine_tier"),
            "AI suggested": d.get("ai_suggested"),
            "Final tier": d.get("final"),
            "Source": d.get("source"),
            "Reason": e.get("reason", ""),
        })
    elif agent == "comms" and action == "sent":
        srcs = d.get("sources", {})
        comms.append({
            "Crew": d.get("crew"),
            "Tier": tier_name(d.get("tier")),
            "Languages": ", ".join(d.get("languages", [])),
            "AI-drafted": ", ".join(k for k, v in srcs.items() if v == "ai-draft") or "none",
        })
    elif agent == "escalation" and action == "emergency":
        emergencies += 1

df = pd.DataFrame(decisions)

raised = 0
if not df.empty:
    raised = int((df["Final tier"] > df["Engine tier"]).sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Assessments", len(df))
c2.metric("Raised by AI", raised)
c3.metric("Emergencies", emergencies)
c4.metric("Alerts sent", len(comms))
c5.metric("Audit chain linked", "Yes" if chain_linked(rows) else "BROKEN")

if not df.empty:
    st.subheader("Tier over time, by crew")
    pivot = df.pivot_table(index="Time", columns="Crew", values="Final tier", aggfunc="max")
    st.line_chart(pivot)
    st.caption("0 = Green, 1 = Yellow, 2 = Orange, 3 = Red, 4 = Emergency")

    st.subheader("Decisions")
    show = df.copy()
    for col in ["Engine tier", "AI suggested", "Final tier"]:
        show[col] = show[col].apply(tier_name)
    st.dataframe(show, witdth=''stretch'', hide_index=True)

if comms:
    st.subheader("Worker alerts sent")
    st.dataframe(pd.DataFrame(comms), width="stretch", hide_index=True)
    st.caption("AI-drafted translations must be reviewed by a native speaker before real deployment.")

with st.expander("Raw audit entries (last 20)"):
    st.json(rows[-20:])