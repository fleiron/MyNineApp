import os, time, uuid
from typing import List, Literal, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

# --- Config ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Ротация по моделям v1 (можешь менять порядок приоритетов)
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

# --- Data models ---
class ChatTurn(BaseModel):
    role: Literal["user","partner","other"] = "other"
    text: str = Field(..., min_length=1, max_length=2000)

Relationship = Literal["girlfriend","boyfriend","friend","coworker","boss","stranger","family","other"]
Scenario = Literal[
    "defuse_tension","apologize","flirt","ask_out","schedule","negotiate",
    "follow_up","reject_politely","say_no","clarify","congratulate","thank","other"
]
Tone = Literal["confident","friendly","neutral","apologetic","playful","flirty","formal","direct","other"]

class GenerateRequest(BaseModel):
    messages: List[ChatTurn]
    relationship: Relationship = "other"
    scenario: Scenario = "other"
    tone: Tone = "neutral"
    language: Optional[str] = None  # if None => auto-detect by model
    target_gender: Optional[Literal["male","female","other"]] = None
    personalness: int = Field(50, ge=0, le=100)  # 0=formal, 100=very personal
    intensify: Optional[Literal["softer","edgier"]] = None  # UI: Make softer/Make edgier

class ReplyOption(BaseModel):
    label: str  # e.g. "Confident", "Friendly", "Original"
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
    by_language: dict
    by_scenario: dict
    conversion_rate_guess: float

# --- in-memory analytics (for MVP; swap to Redis/DB later) ---
ANALYTICS = {
    "total_generations": 0,
    "by_language": {},
    "by_scenario": {},
    "chosen": 0,
}

# --- Prompt template ---
PROMPT_TEMPLATE = """You are an AI assistant that helps craft short, natural-sounding messenger replies.
Context:
- Relationship type: {relationship}
- Scenario/goal: {scenario}
- Desired tone: {tone}
- Target gender (if any): {target_gender}
- Personalness (0=formal, 100=very personal): {personalness}
Rules:
- Reply in the SAME LANGUAGE as the conversation{lang_hint}.
- Max 2–3 sentences. Sound human, not robotic.
- Adapt to the emotional context; be concise and tactful.
- Add humor, empathy, or light flirt only if appropriate for scenario and relationship.
- Provide THREE stylistically distinct options:
  1) Confident & clear
  2) Friendly & warm
  3) Original with a tasteful twist (playful/flirty/clever—if appropriate)
Intensity adjuster: {intensify_note}
Recent conversation (latest last):
{formatted}
Return ONLY a JSON with keys: language (iso guess) and options=[{{"label": "...","text": "..."}}, ...].
"""

def format_dialog(msgs: List[ChatTurn]) -> str:
    lines = []
    for m in msgs[-8:]:  # last 8 turns for focus
        who = {"user":"You","partner":"Partner"}.get(m.role, "Other")
        lines.append(f"{who}: {m.text}")
    return "\n".join(lines)

def build_prompt(payload: GenerateRequest) -> str:
    formatted = format_dialog(payload.messages)
    lang_hint = f" (target language: {payload.language})" if payload.language else ""
    intensify_note = {
        None: "neutral baseline",
        "softer": "make responses a little softer and gentler",
        "edgier": "make responses a little bolder and edgier (but still respectful)",
    }[payload.intensify]
    return PROMPT_TEMPLATE.format(
        relationship=payload.relationship,
        scenario=payload.scenario,
        tone=payload.tone,
        target_gender=payload.target_gender or "unspecified",
        personalness=payload.personalness,
        lang_hint=lang_hint,
        formatted=formatted,
        intensify_note=intensify_note,
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

    # Корректные safety для v1 (можно отключить через DISABLE_SAFETY=1)
    if not DISABLE_SAFETY:
        body["safetySettings"] = [
            {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HARASSMENT",         "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",  "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT",  "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY",    "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]

    # Ротация по моделям до первого успешного ответа
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
    # Gemini returns text in candidates[0].content.parts[*].text
    try:
        parts = gemini_json["candidates"][0]["content"]["parts"]
        texts = [p.get("text","") for p in parts if "text" in p]
        return "\n".join(texts)
    except Exception as e:
        return ""

import json
def safe_parse_options(text_blob: str) -> GenerateResponse:
    # Try to parse JSON block; if fails, fallback to a safe triple
    try:
        data = json.loads(text_blob.strip())
        language = data.get("language")
        opts = [ReplyOption(**o) for o in data.get("options", [])][:3]
        if len(opts) < 3:  # pad
            while len(opts) < 3:
                opts.append(ReplyOption(label="Friendly", text="Got it!"))
        return GenerateResponse(id=str(uuid.uuid4()), language=language, options=opts)
    except Exception:
        # Very defensive fallback
        sample = [
            ReplyOption(label="Confident", text="I hear you. Let me make it right—can we talk tonight?"),
            ReplyOption(label="Friendly", text="Sorry for the delay! I do care—how about we fix this together?"),
            ReplyOption(label="Original", text="I owe you one. Coffee truce and we reset the tone?"),
        ]
        return GenerateResponse(id=str(uuid.uuid4()), language=None, options=sample)

# --- Routes ---
@app.get("/health")
def health():
    return {"ok": True, "ts": int(time.time())}

@app.post("/generate_reply", response_model=GenerateResponse)
async def generate_reply(req: GenerateRequest):
    prompt = build_prompt(req)
    raw = await call_gemini(prompt)
    text_blob = extract_json_text(raw)
    parsed = safe_parse_options(text_blob)
    # update analytics
    ANALYTICS["total_generations"] += 1
    lang_key = (parsed.language or req.language or "auto")
    ANALYTICS["by_language"][lang_key] = ANALYTICS["by_language"].get(lang_key, 0) + 1
    ANALYTICS["by_scenario"][req.scenario] = ANALYTICS["by_scenario"].get(req.scenario, 0) + 1
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
