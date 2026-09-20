---
title: Etsy Review Intelligence
emoji: 🛍️
colorFrom: yellow
colorTo: yellow
sdk: docker
app_port: 7860
fullWidth: true
short_description: AI sentiment and topic analysis for Etsy reviews.
---

# Etsy Review Intelligence

An end-to-end review intelligence platform that turns Etsy customer feedback into product, customer-experience, and marketing insights. Submit one to ten Etsy listing IDs or URLs to collect reviews, analyse sentiment, discover recurring themes, and compare product satisfaction in an interactive dashboard.

## Highlights

- Built a FastAPI backend and React dashboard that ingest 1–10 Etsy listing IDs, retrieve reviews through the Etsy Open API, and save analysis reports as JSON.
- Ranks products with a customer-satisfaction score weighted from review-text sentiment (60%) and average star rating (40%).
- Fine-tuned a domain-adapted DistilBERT sentiment classifier and developed an explainable topic-discovery pipeline for actionable review analytics.

## Architecture

```text
Etsy listing ID / URL
        │
        ▼
FastAPI API ──► Etsy Open API ──► Review records
        │                              │
        ▼                              ▼
React dashboard ◄── JSON reports ◄── NLP analysis pipeline
```

The API validates requests, fetches every available review page for each listing, performs analysis, persists the response in `data/`, and returns the report to the dashboard. A single listing produces a detailed report; multiple listings produce a ranked comparison.

## Sentiment model: fine-tuning and evaluation

The model was fine-tuned from `distilbert-base-uncased-finetuned-sst-2-english` using a balanced 2,000-sample subset of Amazon Electronics reviews:

- **Labels:** 1–2 star reviews as negative; 4–5 star reviews as positive; 3-star reviews excluded.
- **Data split:** 80/20 stratified train/test split, giving 400 held-out test reviews.
- **Training:** 3 epochs, maximum sequence length of 256, learning rate of `2e-5`.
- **Selection metric:** F1 score, with evaluation and checkpointing after every epoch.

| Model | Held-out accuracy | F1 score |
| --- | ---: | ---: |
| Base SST-2 model | 83.8% | 82.1% |
| Fine-tuned Amazon-review model | **93.8%** | **93.7% macro F1** |

The fine-tuned classifier improved accuracy by **10.0 percentage points** and macro F1 by **11.6 percentage points** over the baseline on the same held-out test set. The reproducible experiment, metric comparison, and confusion matrix are available in [`fine_tune_distilbert_amazon_reviews.ipynb`](fine_tune_distilbert_amazon_reviews.ipynb).

## Explainable NLP analytics

Beyond positive/negative classification, the pipeline produces interpretable review intelligence:

- **Sentiment analysis:** fine-tuned DistilBERT scores each review and identifies rating-versus-text mismatches.
- **Key-phrase extraction:** identifies frequent terms and bigrams with their average sentiment.
- **Topic extraction and clustering:** embeds review sentences with `paraphrase-multilingual-MiniLM-L12-v2`, reduces embeddings with UMAP, and groups recurring themes using HDBSCAN.
- **Explainability and diagnostics:** assigns semantic labels from centroid-nearest phrases; reports DBCV, silhouette score, noise ratio, cluster confidence, representative reviews, and sentiment breakdown per topic.
- **Visual analytics:** interactive sentiment distribution, rating-versus-sentiment plot, topic-risk analysis, 2D intertopic distance map, and sentiment/topic trends over time.

## Technology stack

| Layer | Technologies |
| --- | --- |
| API and data collection | FastAPI, Uvicorn, Requests, Etsy Open API |
| Frontend | React, Vite, Lucide React, custom CSS |
| Sentiment ML | PyTorch, Hugging Face Transformers, fine-tuned DistilBERT |
| Topic modelling | Sentence-Transformers, UMAP, HDBSCAN, scikit-learn |
| Training and evaluation | Hugging Face Datasets/Trainer, pandas, scikit-learn, Matplotlib, Seaborn |

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Etsy API credentials

### Install dependencies

```powershell
.\.venv311\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "import nltk; nltk.download('stopwords')"

Push-Location frontend
npm install
Pop-Location
```

Create `.env` in the project root:

```env
ETSY_API_KEY="your_etsy_keystring"
ETSY_API_SECRET="your_etsy_shared_secret"
ETSY_API_BASE_URL="https://openapi.etsy.com/v3"
```

### Run locally

Run the production-style application:

```powershell
python app.py
```

Open `http://localhost:8000` after building the frontend:

```powershell
Push-Location frontend
npm run build
Pop-Location
```

For frontend development, use two terminals:

```powershell
# Terminal 1
python app.py

# Terminal 2
Push-Location frontend
npm run dev
```

Open the Vite application at `http://localhost:5173`.

## API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/reports` | List saved reports |
| `GET` | `/api/reports/{filename}` | Load a saved report |
| `POST` | `/api/analyze` | Analyse one to ten Etsy listing IDs or URLs |

Example request:

```json
{
  "listing_ids": ["4364973626", "1234567890"]
}
```

## Deploy to Hugging Face Spaces

This repository is configured as a Docker Space. Create a Hugging Face Space with the **Docker** SDK, then push this repository. The included `Dockerfile` builds the React frontend and serves FastAPI on port `7860`.

In **Settings → Variables and secrets**, add:

```text
ETSY_API_KEY
ETSY_API_SECRET
```

Optionally add:

```text
ETSY_API_BASE_URL=https://openapi.etsy.com/v3
```

Model weights and training checkpoints are excluded from Git. Before building the Docker image, run `fine_tune_distilbert_amazon_reviews.ipynb` to generate the model, or restore your saved model to `models/distilbert-amazon-reviews/final`.

Only the production model in `models/distilbert-amazon-reviews/final` is included in the Docker build; training checkpoints and local reports are excluded. Standard Hugging Face Space storage is ephemeral, so use persistent storage or a database if reports must survive restarts.

## Project structure

```text
├── app.py                                  # FastAPI routes and report persistence
├── etsy_reviews_service.py                 # Etsy API collection and pagination
├── sentiment_analysis.py                   # Sentiment, phrase, and topic analysis
├── fine_tune_distilbert_amazon_reviews.ipynb
├── models/distilbert-amazon-reviews/final  # Fine-tuned inference model
├── frontend/                               # React/Vite dashboard
├── Dockerfile                              # Hugging Face Docker Space build
└── requirements.txt
```
