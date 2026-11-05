from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Crew:
    crew_id: str
    zone: str
    size: int
    task: str                 # "light" | "moderate" | "heavy"
    ppe: str                  # "std" | "full"
    acclimatised: bool
    languages: List[str] = field(default_factory=lambda: ["en"])


@dataclass
class Reading:
    zone: str
    time: str                 # e.g. "09:30"
    wbgt: Optional[float]     # None = every sensor failed
    forecast_2h: Optional[float] = None
    network_up: bool = True
    sensor_ok: bool = True


@dataclass
class SymptomReport:
    crew_id: str
    time: str
    red_flag: bool = True     # confusion, collapse, no sweating, severe headache or vomiting


@dataclass
class RiskResult:
    tier: int                 # 0 Green .. 3 Red, 4 Emergency
    name: str
    limit: float
    effective_wbgt: Optional[float]
    margin: Optional[float]
    forecast_margin: Optional[float]
    reason: str
    fallback_protocol: bool = False
