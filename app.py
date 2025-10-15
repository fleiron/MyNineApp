import os, time, uuid, json, re
from typing import List, Optional, Dict
from enum import Enum
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

# --- Config ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_ENDPOINTS = [
    "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent",
    "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash-001:generateContent",
    "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash-lite-001:generateContent",
    "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent",
]
DISABLE_SAFETY = os.getenv("DISABLE_SAFETY", "0") == "1"

# --- FastAPI ---
app = FastAPI(title="TextSense API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- Enums (надёжнее, чем Literal, на разных рантаймах) ---
class Role(str, Enum):
    user = "user"
    partner = "partner"
    other = "other"

class Relationship(str, Enum):
    girlfriend = "girlfriend"
    boyfriend  = "boyfriend"
    friend     = "friend"
    coworker   = "coworker"
    boss       = "boss"
    stranger   = "stranger"
    family     = "family"
    other      = "other"

class Scenario(str, Enum):
    defuse_tension    = "defuse_tension"
    apologize         = "apologize"
    flirt             = "flirt"
    ask_out           = "ask_out"
    schedule          = "schedule"
    negotiate         = "negotiate"
    follow_up         = "follow_up"
    reject_politely   = "reject_politely"
    say_no            = "say_no"
    clarify           = "clarify"
    congratulate      = "congratulate"
    thank             = "thank"
    other             = "other"

class Tone(str, Enum):
    confident   = "confident"
    friendly    = "friendly"
    neutral     = "neutral"
    apologetic  = "apologetic"
    playful     = "playful"
    flirty      = "flirty"
    formal      = "formal"
    direct      = "direct"
    other       = "other"

class Gender(str, Enum):
    male   = "male"
    female = "female"
    other  = "other"

class Intensify(str, Enum):
    softer = "softer"
    edgier = "edgier"

# --- Data models ---
class ChatTurn(BaseModel):
    role: Role = Role.other
    text: str = Field(..., min_length=1, max_length=2000)

class GenerateRequest(BaseModel):
    messages: List[ChatTurn]
    relationship: Relationship = Relationship.other
    scenario: Scenario = Scenario.other
    tone: Tone = Tone.neutral
    language: Optional[str] = None          # if None => auto-detect
    target_gender: Optional[Gender] = None
    personalness: int = Field(50, ge=0, le=100)  # 0=formal, 100=very personal
    intensify: Optional[Intensify] = None        # Make softer / Make edgier

class ReplyOption(BaseModel):
    label: str
    text: str

class GenerateResponse(BaseModel):
    id: str
    language: Optional[str]
    options: List[ReplyOption]

class FeedbackRequest(BaseModel):
    generation_id: str
    chosen_label: Optional[str] = None
    chosen_text: Optional[str] = None
    dismissed_labels: Optional[List[str]] = None
    liked: Optional[bool] = None

class StatsResponse(BaseModel):
    total_generations: int
    by_language: Dict[str, int]
    by_scenario: Dict[str, int]
    conversion_rate_guess: float

# --- in-memory analytics ---
ANALYTICS = {
    "total_generations": 0,
    "by_language": {},
    "by_scenario": {},
    "chosen": 0,
}

# --- Simple language detection (EN/ES/DE/IT/RU) ---
_LATIN_PUNCT_HINTS = {
    "es": ["¿", "¡", "hola", "gracias", "por qué", "buenos", "tú", "usted", "perdón"],
    "de": ["ß", "ä", "ö", "ü", "und", "nicht", "danke", "hallo", "bitte", "ich", "du"],
    "it": ["ciao", "grazie", "perché", "sei", "sono", "andiamo", "scusa", "prego"],
    "en": ["the", "and", "you", "thanks", "hello", "sorry", "please", "hi"],
}

def _contains_cyrillic(s: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", s))

def detect_language_from_messages(msgs: List[ChatTurn]) -> Optional[str]:
    """
    Lightweight heuristic:
      - If any Cyrillic → 'ru'
      - Else scan last messages for hints among {es,de,it,en}
      - Else None (fallback to model)
    """
    if not msgs:
        return None
    last_texts = [m.text for m in msgs if m.text.strip()]
    if not last_texts:
        return None
    combined = " \n".join(last_texts[-6:])

    if _contains_cyrillic(combined):
        return "ru"

    # Check last message first
    candidates = [last_texts[-1]] + last_texts[:-1]
    for lang_try in candidates:
        lt = lang_try.lower()
        if "¿" in lt or "¡" in lt:
            return "es"
        scores = {k: 0 for k in _LATIN_PUNCT_HINTS}
        for code, hints in _LATIN_PUNCT_HINTS.items():
            for h in hints:
                if h in lt:
                    scores[code] += 1
        best = max(scores, key=lambda k: scores[k])
        if scores[best] >= 2:
            return best

    lt = combined.lower()
    if any(h in lt for h in _LATIN_PUNCT_HINTS["es"]): return "es"
    if any(h in lt for h in _LATIN_PUNCT_HINTS["de"]): return "de"
    if any(h in lt for h in _LATIN_PUNCT_HINTS["it"]): return "it"
    if any(h in lt for h in _LATIN_PUNCT_HINTS["en"]): return "en"
    return None

# --- Prompt template ---
PROMPT_TEMPLATE = """You are an AI assistant that helps craft short, natural-sounding messenger replies.
Context:
- Relationship type: {relationship}
- Scenario/goal: {scenario}
- Desired tone: {tone}
- Target gender (if any): {target_gender}
- Personalness (0=formal, 100=very personal): {personalness}
Rules:
- Reply STRICTLY in this target language: {target_lang}. If conversation is mixed, prefer the partner's latest message language.
- Keep answers in 2–3 sentences. Sound human, not robotic.
- Adapt to the emotional context; be concise and tactful.
- Add humor, empathy, or light flirt only if appropriate for scenario and relationship.
- Provide THREE stylistically distinct options:
  1) Confident & clear
  2) Friendly & warm
  3) Original with a tasteful twist (playful/flirty/clever—if appropriate)
- Return ONLY a JSON object with keys: language (ISO code) and options=[{{"label": "...","text": "..."}}, ...].
- Do not include markdown, backticks or any extra text.
Intensity adjuster: {intensify_note}
Recent conversation (latest last):
{formatted}
"""

def format_dialog(msgs: List[ChatTurn]) -> str:
    lines = []
    for m in msgs[-8:]:
        who = {Role.user: "You", Role.partner: "Partner"}.get(m.role, "Other")
        lines.append(f"{who}: {m.text}")
    return "\n".join(lines)

def build_prompt(payload: GenerateRequest, target_lang: str) -> str:
    formatted = format_dialog(payload.messages)
    intensify_note = {
        None: "neutral baseline",
        Intensify.softer: "make responses a little softer and gentler",
        Intensify.edgier: "make responses a little bolder and edgier (but still respectful)",
    }[payload.intensify]
    return PROMPT_TEMPLATE.format(
        relationship=payload.relationship.value,
        scenario=payload.scenario.value,
        tone=payload.tone.value,
        target_gender=(payload.target_gender.value if payload.target_gender else "unspecified"),
        personalness=payload.personalness,
        intensify_note=intensify_note,
        formatted=formatted,
        target_lang=target_lang,
    )

async def call_gemini(prompt: str) -> dict:
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Missing GEMINI_API_KEY")

    body = {
        "contents": [ { "role": "user", "parts": [ { "text": prompt } ] } ],
        "generationConfig": {
            "temperature": 0.9, "topP": 0.95, "topK": 40, "maxOutputTokens": 512
        }
    }

    if not DISABLE_SAFETY:
        body["safetySettings"] = [
            {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HARASSMENT",         "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",  "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT",  "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY",    "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]

    last_err = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for url_base in GEMINI_ENDPOINTS:
            url = f"{url_base}?key={GEMINI_API_KEY}"
            r = await client.post(url, json=body)
            if 200 <= r.status_code < 300:
                return r.json()
            last_err = r.text
    raise HTTPException(status_code=502, detail=f"Gemini error: {last_err}")

def extract_json_text(gemini_json: dict) -> str:
    try:
        parts = gemini_json["candidates"][0]["content"]["parts"]
        texts = [p.get("text","") for p in parts if isinstance(p, dict) and "text" in p]
        return "\n".join(texts)
    except Exception:
        return ""

def safe_parse_options(text_blob: str) -> GenerateResponse:
    try:
        data = json.loads(text_blob.strip())
        language = data.get("language")
        opts_raw = data.get("options", [])
        opts: List[ReplyOption] = []
        for o in opts_raw[:3]:
            label = (o.get("label") or "Option")
            text  = (o.get("text") or "")
            opts.append(ReplyOption(label=label, text=text))
        while len(opts) < 3:
            opts.append(ReplyOption(label="Friendly", text="Got it!"))
        return GenerateResponse(id=str(uuid.uuid4()), language=language, options=opts)
    except Exception:
        sample = [
            ReplyOption(label="Confident", text="I hear you. Let me make it right—can we talk tonight?"),
            ReplyOption(label="Friendly",  text="Sorry for the delay! I do care—how about we fix this together?"),
            ReplyOption(label="Original",  text="I owe you one. Coffee truce and we reset the tone?"),
        ]
        return GenerateResponse(id=str(uuid.uuid4()), language=None, options=sample)

# --- Routes ---
@app.get("/health")
def health():
    return {"ok": True, "ts": int(time.time())}

@app.post("/generate_reply", response_model=GenerateResponse)
async def generate_reply(req: GenerateRequest):
    # Choose language: explicit > detected > default en
    lang = (req.language or detect_language_from_messages(req.messages) or "en")
    prompt = build_prompt(req, target_lang=lang)
    raw = await call_gemini(prompt)
    text_blob = extract_json_text(raw)
    parsed = safe_parse_options(text_blob)
    if not parsed.language:
        parsed.language = lang

    ANALYTICS["total_generations"] += 1
    ANALYTICS["by_language"][parsed.language] = ANALYTICS["by_language"].get(parsed.language, 0) + 1
    ANALYTICS["by_scenario"][req.scenario.value] = ANALYTICS["by_scenario"].get(req.scenario.value, 0) + 1
    return parsed

@app.post("/feedback")
def feedback(req: FeedbackRequest):
    if req.chosen_text:
        ANALYTICS["chosen"] += 1
    return {"ok": True}

@app.get("/stats", response_model=StatsResponse)
def stats():
    total = max(1, ANALYTICS["total_generations"])
    return StatsResponse(
        total_generations=ANALYTICS["total_generations"],
        by_language=ANALYTICS["by_language"],
        by_scenario=ANALYTICS["by_scenario"],
        conversion_rate_guess=round(ANALYTICS["chosen"]/total, 3),
    )
