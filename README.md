---
title: Aksi
emoji: 👁️
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# Aksi (अक्षि)

Point your phone camera, hold the screen, ask in your own language, and hear the answer.
Built for visually impaired people, entirely on Sarvam AI:

- **Saaras v3**: speech to text, detects the language
- **Gemma 4 on Sarvam**: looks at the photo and answers
- **Bulbul v3**: speaks the answer in the same language

## Run locally

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
# put SARVAM_API_KEY=... in .env
.venv\Scripts\python.exe -m uvicorn main:app --port 8000
```

Phones need an https link for the camera, e.g. `cloudflared tunnel --url http://localhost:8000`.

## Deploy

The `Dockerfile` runs on Hugging Face Spaces or Render. Set `SARVAM_API_KEY` as a secret in the host's settings.
