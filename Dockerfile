FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && python -m nltk.downloader -d /usr/local/share/nltk_data stopwords

RUN useradd --create-home --uid 1000 appuser \
    && chown appuser:appuser /app
USER appuser
ENV HOME=/home/appuser \
    HF_HOME=/home/appuser/.cache/huggingface

COPY --chown=appuser:appuser backend/ ./backend/
RUN python -c "from backend.sentiment_analysis import _embedder; _embedder()"
COPY models/distilbert-amazon-reviews/final ./models/distilbert-amazon-reviews/final
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

EXPOSE 7860

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "7860"]
