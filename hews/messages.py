"""Vetted message templates and message safety checks."""
import re

TEXT = {
 "en": ["Heat is normal. Drink water and use shade.",
        "Heat is rising. Drink water now and check on new workers.",
        "High heat. Take your rest break now, slow down and cool off.",
        "Stop work. Move to shade, cool down and rest. Tell your supervisor.",
        "Possible heat illness. Cool the worker, call 112 or 10177 and the site first-aider."],
 "zu": ["Ukushisa kuvamile. Phuza amanzi futhi usebenzise umthunzi.",
        "Ukushisa kuyakhula. Phuza amanzi manje futhi uhlole abasebenzi abasha.",
        "Ukushisa okukhulu. Phumula manje, wehlise ijubane, uzipholise.",
        "Yeka umsebenzi. Hamba emthunzini, uzipholise futhi uphumule. Tshela umphathi wakho.",
        "Kungenzeka ukugula ngokushisa. Pholisa umuntu, ushayele i-112 noma i-10177, ubize ne-first-aider yesizinda."],
 "st": ["Mocheso o tloaelehile. Noa metsi 'me u sebelise moriti.",
        "Mocheso oa nyoloha. Noa metsi hona joale 'me u hlahlobe basebetsi ba bacha.",
        "Mocheso o phahameng. Phomola hona joale, fokotsa lebelo 'me u itlose.",
        "Emisa mosebetsi. Eya moriting, u itlose 'me u phomole. Bolella molaoli oa hao.",
        "Ho kanna ha e-ba ho kula ka mocheso. Pholosa motho, letsetsa 112 kapa 10177 'me u memele ea thusang pele."],
 "tn": ["Mogote o tlwaelegile. Nwa metsi o bo o dirise moriti.",
        "Mogote o a oketsega. Nwa metsi jaanong o bo o lekola badiri ba basha.",
        "Mogote o mo godimo. Ikhutse jaanong, fokotsa lebelo o bo o itsididise.",
        "Emisa tiro. Ya mo moriting, o itsididise o bo o ikhutse. Bolelela molebedi wa gago.",
        "Go ka nna bolwetse jwa mogote. Tsididisa motho, founela 112 kana 10177 o bo o bitsa motlhokomedi wa kalafi ya ntlha."],
}
LANG_NAMES = {"en": "English", "zu": "isiZulu", "st": "Sesotho", "tn": "Setswana", "nso": "Sepedi", "ts": "Xitsonga"}
WORK_REST = ["Normal schedule", "45 min work, 15 min rest", "30 min work, 30 min rest",
             "Stop non-essential work", "Emergency response"]
ACTION = ["Normal work. Keep water and shade available.",
          "Drink water now. Check shade and new workers.",
          "Take rest breaks now. Cut intensity and cool down.",
          "Stop non-essential work. Cool down, rest, check for symptoms.",
          "Cool the worker, call 112 or 10177, alert the site first-aider."]

PHONE = re.compile(r"\+?\d[\d\s-]{8,}\d")


def template(tier: int, lang: str):
    """Vetted text, or None if we have no vetted translation for this language."""
    t = TEXT.get(lang)
    return t[tier] if t else None


def validate(text: str, tier: int):
    """Safety checks on any outgoing worker message. Returns (ok, problems)."""
    problems = []
    if not text or not text.strip():
        problems.append("empty")
        return False, problems
    if len(text) > 280:
        problems.append("too long for SMS/WhatsApp preview")
    if PHONE.search(text.replace("10177", "").replace("112", "")):
        problems.append("contains a phone-number-like string")
    if tier == 4 and not ("112" in text or "10177" in text):
        problems.append("emergency message must include 112 or 10177")
    if tier >= 3 and not any(w in text.lower() for w in ("stop", "emisa", "yeka", "emergency", "heat illness", "ukugula", "ho kula", "bolwetse")):
        problems.append("Red/Emergency message must clearly say to stop or give the emergency action")
    return (not problems), problems
