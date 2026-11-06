# Zanti HEWS v2: the agent team
**Live dashboard:** https://zanti-hews.streamlit.app/ (shows a sample run; AI agents run on Azure AI Foundry, GPT-5.2)

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
### Azure AI Foundry (used for the hackathon demo)

The agents run on a GPT-5.2 deployment in Azure AI Foundry. In PowerShell (Windows):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:HEWS_PROVIDER = "azure"
$env:AZURE_OPENAI_ENDPOINT = "https://<your-resource>.services.ai.azure.com/"
$env:AZURE_OPENAI_API_KEY = "<your-key>"
$env:AZURE_OPENAI_DEPLOYMENT = "<your-deployment-name>"
python -m hews.run
```

Keys are read from environment variables only and are never stored in the repository. See `.env.example` for the variable names. If Azure is not configured, or any AI call fails, every agent falls back to its deterministic behaviour, so the system keeps working offline.
To use the Claude API instead: `export ANTHROPIC_API_KEY=...` then `python -m hews.run`.
### Dashboard

A Streamlit dashboard reads the audit log and shows tier changes per crew, where the AI raised a tier, worker alerts sent (with the languages the AI drafted), emergencies, and whether the audit chain is intact.

```powershell
python -m hews.run
streamlit run dashboard.py
```

The dashboard opens at http://localhost:8501. Use the sidebar to switch between your latest run (`out/audit.jsonl`) and the sample log in `docs/`. The sample log works without running anything, so the dashboard can be viewed straight after cloning.

### Evidence: audit trail

`docs/sample_audit.jsonl` holds the first 15 entries of a real run with Azure AI Foundry enabled. Each entry records the agent, its action and the crew-level data it used, and is chained to the previous entry by a hash, so any edit to the log breaks the chain. The entries show the guardrails working:

- The assessor logs what the AI suggested, what the deterministic engine said, and the final tier. The AI can only raise a tier, never lower it.
- The comms agent logs where each language came from: `vetted-template` for reviewed text, or `ai-draft` for languages with no vetted text.
- No individual health data is stored. Entries contain crew-level information only.

AI-drafted translations (for example Sepedi) must be reviewed by a native speaker before any real deployment.
Status: version 2.0 core. Messages are dry-run (printed, not sent). Live WhatsApp/SMS sending,
real sensor feeds and the supervisor dashboard come next. Thresholds are illustrative and need
calibration with an occupational-health physician.

### Responsible AI

The design follows Microsoft's four-stage process for generative AI (Map, Measure, Mitigate, Manage), which lines up with the NIST AI Risk Management Framework.

- **Map:** the harms we identified are an AI weakening a safety decision, wrong or unvetted translations, exposure of worker health data, misuse for discipline, alert fatigue, and AI failure.
- **Measure:** the audit log records the engine tier, the AI's suggested tier and the final tier for every cycle, so the AI's influence can be counted. The daily report counts AI raises, fallback uses and emergencies, and automated tests in `tests/` cover the pipeline. Missed-event and false-alarm rates are pilot measures.
- **Mitigate (layered):** the AI may only raise a tier, never lower it or declare an emergency. The emergency protocol uses no AI. An auditor checks outgoing messages and blocks unsafe or private content. AI agents see crew-level context only, and AI-drafted translations are labelled. Invalid AI output falls back to vetted text and the rules engine.
- **Manage:** alerts are dry-run until a pilot site agrees. Supervisors and clinicians make the final decisions, thresholds are calibrated with an occupational-health physician, AI-drafted translations are reviewed by native speakers, and the hash-chained audit log supports review.

Known limitations of the underlying service and model are reviewed using the Azure OpenAI transparency note (https://learn.microsoft.com/en-us/legal/cognitive-services/openai/transparency-note) and the model developer's documentation. A Responsible AI Impact Assessment, using Microsoft's template, is planned before any pilot.
