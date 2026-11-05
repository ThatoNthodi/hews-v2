# Zanti HEWS v2: the agent team

HEWS stands for Heat Early Warning System. Version 2 replaces the single rules page with a team of agents that
each do one job, with safety rules the AI cannot break.

## The team

| Agent | Job | Uses AI? |
|---|---|---|
| Risk engine | Computes the alert tier from conditions and crew context | No (deterministic) |
| Assessor | Reviews the tier and may only make it MORE cautious | Yes, with a guardrail |
| Comms | Sends vetted alerts in the worker's language; AI drafts only languages we have no vetted text for | Partly |
| Supervisor Advisor | Crew-level work-rest plan and outlook; never sees individuals | Yes, output is checked |
| Escalation | Emergency protocol and first-aider alert | No, by design |
| Auditor | Blocks unsafe or private content, keeps a tamper-evident log, makes de-identified reports | No |
| Orchestrator (`team.py`) | Runs the team, one alert per tier change | No |

## Safety rules built into the code

1. An AI suggestion can only raise the tier, never lower it, and can never declare an Emergency.
2. Emergency messages and the emergency protocol never use the AI.
3. Every outgoing message is checked (length, no phone numbers, emergency numbers present).
4. The supervisor view is checked and cannot contain individual health data.
5. Any AI failure or bad output falls back to vetted text and the deterministic engine.
6. Every decision is written to a hash-chained audit log.

## Run it

```bash
python -m venv .venv
source .venv/Scripts/activate        # Git Bash on Windows
pip install -r requirements.txt
python -m pytest -q tests            # 12 tests should pass
python -m hews.run --offline         # simulated day, no AI needed
```

To use AI agents for free with a local model (Ollama): `export HEWS_PROVIDER=ollama` then `python -m hews.run`.
To use the Claude API instead: `export ANTHROPIC_API_KEY=...` then `python -m hews.run`.

Status: version 2.0 core. Messages are dry-run (printed, not sent). Live WhatsApp/SMS sending,
real sensor feeds and the supervisor dashboard come next. Thresholds are illustrative and need
calibration with an occupational-health physician.
