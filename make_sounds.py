"""One-time script: pre-record the "something went wrong" clip in every language with Bulbul.

    python make_sounds.py

Saves static/sounds/error-<lang>.wav. The phone loads these in advance, so the error
message still plays when the internet or Sarvam is down.
"""

import base64
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

ERRORS = {
    "hi-IN": "कुछ गड़बड़ हो गई, फिर से कोशिश कीजिए।",
    "mr-IN": "काहीतरी चुकले, पुन्हा प्रयत्न करा.",
    "te-IN": "ఏదో తప్పు జరిగింది. మళ్ళీ ప్రయత్నించండి.",
    "ta-IN": "ஏதோ தவறு நடந்தது. மீண்டும் முயலுங்கள்.",
    "kn-IN": "ಏನೋ ತಪ್ಪಾಗಿದೆ. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
    "ml-IN": "എന്തോ തെറ്റ് സംഭവിച്ചു. വീണ്ടും ശ്രമിക്കുക.",
    "bn-IN": "কিছু ভুল হয়েছে, আবার চেষ্টা করুন।",
    "gu-IN": "કંઈક ખોટું થયું, ફરી પ્રયાસ કરો.",
    "pa-IN": "ਕੁਝ ਗਲਤ ਹੋ ਗਿਆ, ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
    "od-IN": "କିଛି ଭୁଲ ହେଲା, ପୁଣି ଚେଷ୍ଟା କରନ୍ତୁ।",
    "en-IN": "Something went wrong. Please try again.",
}

os.makedirs("static/sounds", exist_ok=True)
http = httpx.Client(timeout=60, headers={"api-subscription-key": os.getenv("SARVAM_API_KEY", "")})

for lang, text in ERRORS.items():
    r = http.post("https://api.sarvam.ai/text-to-speech", json={
        "text": text, "language_code": lang, "model": "bulbul:v3", "speech_sample_rate": 16000})
    if r.status_code != 200:
        print(f"FAIL {lang}: {r.status_code} {r.text[:200]}")
        continue
    path = f"static/sounds/error-{lang}.wav"
    with open(path, "wb") as f:
        f.write(base64.b64decode(r.json()["audios"][0]))
    print(f"saved {path} ({os.path.getsize(path) // 1024} KB)")
