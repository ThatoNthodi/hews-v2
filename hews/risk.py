"""Deterministic risk engine. This is the safety core: AI agents may make advice
MORE cautious, never less (see final_tier)."""
from typing import Optional
from .schemas import Crew, Reading, RiskResult

NAMES = ["Green", "Yellow", "Orange", "Red", "Emergency"]
# Illustrative WBGT limits (deg C). To be calibrated with an occupational-health physician.
LIMITS = {True: {"light": 31.0, "moderate": 28.0, "heavy": 26.0},
          False: {"light": 29.0, "moderate": 26.0, "heavy": 24.0}}


def assess(crew: Crew, reading: Reading) -> RiskResult:
    limit = LIMITS[crew.acclimatised][crew.task]
    adj = (3.0 if crew.ppe == "full" else 0.0) + (0.0 if reading.sensor_ok else 1.5) + (0.0 if reading.network_up else 0.5)
    ctx = f"{crew.task} task, {'heavy PPE' if crew.ppe == 'full' else 'standard PPE'}, {'acclimatised' if crew.acclimatised else 'unacclimatised'}"
    forecast = reading.forecast_2h if reading.network_up else None   # forecast needs the cloud

    if reading.wbgt is None:
        # Every sensor failed: conservative fixed work-rest protocol (Orange), more if the forecast is high.
        fm = (forecast + adj - limit) if forecast is not None else None
        tier = 3 if (fm is not None and fm >= 2) else 2
        return RiskResult(tier, NAMES[tier], limit, None, None, fm,
                          f"All sensors failed. Fixed work-rest protocol applies ({ctx}).", fallback_protocol=True)

    eff = reading.wbgt + adj
    m = eff - limit
    fm = (forecast + adj - limit) if forecast is not None else None
    if m >= 2:
        tier = 3
    elif m >= 0:
        tier = 2
    elif m >= -3 or (fm is not None and fm >= 0):
        tier = 1
    else:
        tier = 0
    reason = f"Effective WBGT {eff:.1f} C against a crew limit of {limit:.0f} C ({ctx})."
    return RiskResult(tier, NAMES[tier], limit, eff, m, fm, reason)


def final_tier(engine_tier: int, suggested: Optional[int] = None, red_flag: bool = False) -> int:
    """GUARDRAIL: an AI suggestion can only raise the tier (to at most Red).
    Emergency (4) comes only from a symptom report, never from an AI guess."""
    if red_flag:
        return 4
    t = engine_tier
    if isinstance(suggested, int) and 0 <= suggested <= 3:
        t = max(t, suggested)
    return min(t, 3) if engine_tier < 4 else 4
