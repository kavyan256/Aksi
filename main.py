"""ShowMe server: voice question + photo in, spoken answer out. All three steps use Sarvam."""

import base64
import os
import time

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
SARVAM_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM = "https://api.sarvam.ai"
HEADERS = {"api-subscription-key": SARVAM_KEY}

STT_MODEL = "saaras:v3"   # speech -> text, auto-detects language (v3 benchmarked ~2x faster than v4)
VISION_MODEL = "gemma4"   # photo + question -> answer
TTS_MODEL = "bulbul:v3"   # text -> speech (v3 covers all 11 languages below)

# Languages Bulbul v3 can speak. Anything else is answered in Hindi.
LANGUAGES = {
    "hi-IN": "Hindi", "mr-IN": "Marathi", "te-IN": "Telugu", "ta-IN": "Tamil",
    "kn-IN": "Kannada", "ml-IN": "Malayalam", "bn-IN": "Bengali", "gu-IN": "Gujarati",
    "pa-IN": "Punjabi", "od-IN": "Odia", "en-IN": "English",
}
FALLBACK_LANG = "hi-IN"

NOT_HEARD = "मुझे सुनाई नहीं दिया। स्क्रीन दबाकर रखिए और फिर से पूछिए।"
WELCOME = ("नमस्ते! स्क्रीन दबाकर रखिए, अपनी भाषा में सवाल पूछिए, फिर छोड़ दीजिए। "
           "जवाब दोबारा सुनने के लिए स्क्रीन के सबसे ऊपर छूइए।")

SYSTEM_PROMPT = """You are the eyes of a blind or low-vision person. They point their phone camera and ask a question.
Rules:
- Reply ONLY in {language}, in its native script. Use simple everyday words.
- At most 2 short sentences. No lists, no markdown, no emojis.
- If there is any danger (stairs, step, hole, vehicle, fire, sharp object, obstacle in the path), say it FIRST.
- Give positions as left, right, or straight ahead, and distance in steps (about 1 step = 70 cm).
- Read printed text (medicine names, labels, signs) exactly when asked.
- For Indian currency notes, say the amount clearly.
- If the photo is blurry, dark, or does not show what they asked about, say so and tell them how to move the camera (up, down, left, right, closer, back).
- Never guess. If unsure, say you are not sure."""

app = FastAPI(title="ShowMe")
client = httpx.AsyncClient(timeout=30)
# Pre-recorded error clips made by make_sounds.py
app.mount("/sounds", StaticFiles(directory="static/sounds"), name="sounds")


def check_key():
    if not SARVAM_KEY or SARVAM_KEY == "paste-your-key-here":
        raise HTTPException(500, "SARVAM_API_KEY is not set (.env locally, or the host's secret settings)")


async def sarvam_post(path, **kwargs):
    r = await client.post(f"{SARVAM}{path}", headers=HEADERS, **kwargs)
    if r.status_code != 200:
        raise HTTPException(502, f"Sarvam {path} failed ({r.status_code}): {r.text[:300]}")
    return r.json()


async def transcribe(audio: bytes, filename: str, content_type: str):
    """Saaras: audio -> (text, language code)."""
    data = await sarvam_post(
        "/speech-to-text",
        files={"file": (filename, audio, content_type)},
        data={"model": STT_MODEL, "mode": "transcribe"},
    )
    lang = data.get("language_code") or FALLBACK_LANG
    if lang == "or-IN":  # Saaras may say or-IN for Odia; Bulbul uses od-IN
        lang = "od-IN"
    if lang not in LANGUAGES:
        lang = FALLBACK_LANG
    return (data.get("transcript") or "").strip(), lang


async def look(image: bytes, mime: str, question: str, lang: str):
    """Gemma 4 on Sarvam: photo + question -> short answer in the user's language."""
    image_url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    data = await sarvam_post(
        "/v2/chat/completions",
        json={
            "model": VISION_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(language=LANGUAGES[lang])},
                {"role": "user", "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]},
            ],
            "temperature": 0.2,
            "max_tokens": 150,
        },
    )
    return data["choices"][0]["message"]["content"].strip()


async def speak(text: str, lang: str):
    """Bulbul: text -> base64 WAV audio."""
    data = await sarvam_post(
        "/text-to-speech",
        # 16 kHz is plenty for speech and came back ~2x faster than the 22 kHz default
        json={"text": text[:2500], "language_code": lang, "model": TTS_MODEL, "pace": 1.0,
              "speech_sample_rate": 16000},
    )
    return data["audios"][0]


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.post("/ask-text")
async def ask_text(image: UploadFile = File(...), question: str = Form(...), lang: str = Form("hi-IN")):
    """Phase 2 test: typed question + photo -> text answer (no voice)."""
    check_key()
    if lang not in LANGUAGES:
        raise HTTPException(400, f"lang must be one of {list(LANGUAGES)}")
    t0 = time.perf_counter()
    answer = await look(await image.read(), image.content_type or "image/jpeg", question, lang)
    return {"answer": answer, "seconds": round(time.perf_counter() - t0, 2)}


@app.post("/listen")
async def listen(audio: UploadFile = File(...)):
    """Step 1 for the phone: voice -> question text + language, so the screen can switch language early."""
    check_key()
    t = time.perf_counter()
    question, lang = await transcribe(await audio.read(), audio.filename or "q.webm",
                                      (audio.content_type or "audio/webm").split(";")[0])
    print(f"[listen] {lang} | Q: {question!r} | {round(time.perf_counter() - t, 2)}s")
    return {"question": question, "lang": lang}


@app.post("/answer")
async def answer_question(image: UploadFile = File(...), question: str = Form(""), lang: str = Form(FALLBACK_LANG)):
    """Step 2 for the phone: photo + question -> spoken answer in that language."""
    check_key()
    if lang not in LANGUAGES:
        lang = FALLBACK_LANG
    timings = {}
    if not question.strip():
        answer, lang = NOT_HEARD, FALLBACK_LANG
    else:
        t = time.perf_counter()
        answer = await look(await image.read(), image.content_type or "image/jpeg", question, lang)
        timings["look"] = round(time.perf_counter() - t, 2)
    t = time.perf_counter()
    audio_b64 = await speak(answer, lang)
    timings["speak"] = round(time.perf_counter() - t, 2)
    print(f"[answer] {lang} | A: {answer!r} | {timings}")
    return {"answer": answer, "lang": lang, "audio": audio_b64, "timings": timings}


@app.post("/ask")
async def ask(audio: UploadFile = File(...), image: UploadFile = File(...)):
    """Full loop: voice question + photo -> spoken answer."""
    check_key()
    timings = {}
    t = time.perf_counter()

    question, lang = await transcribe(await audio.read(), audio.filename or "q.webm",
                                      (audio.content_type or "audio/webm").split(";")[0])
    timings["listen"] = round(time.perf_counter() - t, 2)

    if not question:
        answer, lang = NOT_HEARD, FALLBACK_LANG
    else:
        t = time.perf_counter()
        answer = await look(await image.read(), image.content_type or "image/jpeg", question, lang)
        timings["look"] = round(time.perf_counter() - t, 2)

    t = time.perf_counter()
    audio_b64 = await speak(answer, lang)
    timings["speak"] = round(time.perf_counter() - t, 2)

    print(f"[ask] {lang} | Q: {question!r} | A: {answer!r} | {timings}")
    return {"question": question, "lang": lang, "answer": answer, "audio": audio_b64, "timings": timings}


_welcome_cache = None


@app.get("/welcome")
async def welcome():
    """Spoken welcome message, generated once and cached."""
    global _welcome_cache
    check_key()
    if _welcome_cache is None:
        _welcome_cache = await speak(WELCOME, "hi-IN")
    return {"audio": _welcome_cache}
