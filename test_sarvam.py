"""Smoke test for the running server: python test_sarvam.py  (server must be on localhost:8000).

Makes a fake medicine-label photo, then tests speech, vision and the full voice loop.
Answers are saved as WAV files in test_out/ so you can listen to them.
"""

import base64
import io
import os
import sys

import httpx
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()
SERVER = "http://localhost:8000"
OUT = "test_out"
os.makedirs(OUT, exist_ok=True)
http = httpx.Client(timeout=60)


def save_wav(name, b64):
    path = os.path.join(OUT, name)
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    print(f"   saved {path}")


def test_photo():
    """A white medicine strip label with large printed text."""
    img = Image.new("RGB", (800, 500), "white")
    d = ImageDraw.Draw(img)
    try:
        big, small = ImageFont.truetype("arialbd.ttf", 80), ImageFont.truetype("arial.ttf", 40)
    except OSError:
        big = small = ImageFont.load_default()
    d.rectangle([20, 20, 780, 480], outline="blue", width=8)
    d.text((60, 120), "PARACETAMOL", fill="black", font=big)
    d.text((60, 240), "Tablets IP 500 mg", fill="black", font=small)
    d.text((60, 320), "EXP: 08/2027", fill="red", font=small)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def check(name, r):
    if r.status_code != 200:
        print(f"FAIL {name}: {r.status_code} {r.text[:400]}")
        sys.exit(1)
    return r.json()


photo = test_photo()
with open(os.path.join(OUT, "photo.jpg"), "wb") as f:
    f.write(photo)

print("1) Bulbul speech (/welcome)")
save_wav("welcome.wav", check("welcome", http.get(f"{SERVER}/welcome"))["audio"])

print("2) Gemma vision (/ask-text), Marathi")
data = check("ask-text", http.post(f"{SERVER}/ask-text",
             files={"image": ("photo.jpg", photo, "image/jpeg")},
             data={"question": "हे कोणते औषध आहे आणि ते कधी संपते?", "lang": "mr-IN"}))
print(f"   answer: {data['answer']}  ({data['seconds']}s)")

print("3) Full loop (/ask) with a spoken Telugu question")
# Make the spoken question with Bulbul directly, as if a user said it
q = httpx.post("https://api.sarvam.ai/text-to-speech", timeout=60,
               headers={"api-subscription-key": os.getenv("SARVAM_API_KEY")},
               json={"text": "ఇది ఏ మందు?", "language_code": "te-IN", "model": "bulbul:v3"})
if q.status_code != 200:
    print(f"FAIL making question audio: {q.status_code} {q.text[:300]}")
    sys.exit(1)
question_wav = base64.b64decode(q.json()["audios"][0])
data = check("ask", http.post(f"{SERVER}/ask", files={
    "audio": ("q.wav", question_wav, "audio/wav"),
    "image": ("photo.jpg", photo, "image/jpeg")}))
print(f"   heard: {data['question']!r} in {data['lang']}")
print(f"   answer: {data['answer']}")
print(f"   timings: {data['timings']}")
save_wav("answer_telugu.wav", data["audio"])

print("4) Phone flow: /listen then /answer (same Telugu question)")
heard = check("listen", http.post(f"{SERVER}/listen", files={"audio": ("q.wav", question_wav, "audio/wav")}))
print(f"   heard: {heard['question']!r} in {heard['lang']}")
data = check("answer", http.post(f"{SERVER}/answer",
             files={"image": ("photo.jpg", photo, "image/jpeg")},
             data={"question": heard["question"], "lang": heard["lang"]}))
print(f"   answer: {data['answer']}  ({data['lang']}, {data['timings']})")

print("\nAll tests passed.")
