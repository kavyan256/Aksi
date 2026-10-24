# ShowMe server. Works on Hugging Face Spaces (port 7860) and Render (sets $PORT).
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY static ./static

# SARVAM_API_KEY comes from the host's secret settings, never from a file in the image
ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
