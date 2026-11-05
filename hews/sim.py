"""A simulated working day for two crews, including network, sensor and emergency events."""
from .schemas import Crew, Reading, SymptomReport

CREWS = {
    "A": Crew("A", "Block 3 (concrete work)", 12, "heavy", "std", False, ["en", "zu", "nso"]),
    "B": Crew("B", "Yard and loading bay", 8, "light", "std", True, ["en", "tn"]),
}

# (time, A wbgt, B wbgt, forecast_2h, network_up, sensor_ok) ; wbgt None = all sensors failed
TIMELINE = [
    ("08:00", 18.0, 18.0, 21.0, True, True),
    ("09:30", 20.0, 20.0, 23.5, True, True),
    ("10:30", 22.0, 22.0, 25.0, True, True),
    ("11:30", 23.0, 23.0, 27.0, False, True),   # network drops
    ("12:00", 24.0, 24.0, 28.0, True, False),   # a sensor fails
    ("13:00", None, None, 29.0, True, False),   # every sensor fails
    ("14:00", 21.5, 21.5, 25.0, True, True),
]


def events():
    for t, a, b, fc, net, sok in TIMELINE:
        for cid, w in (("A", a), ("B", b)):
            yield ("reading", CREWS[cid], Reading(CREWS[cid].zone, t, w, fc, net, sok))
        if t == "12:00":
            yield ("symptom", CREWS["A"], SymptomReport("A", "12:30"))
