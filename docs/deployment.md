# Deployment

## Docker

Prepare `models/distilbert-amazon-reviews/final/` using the training notebook or a saved export before building. The Dockerfile copies that directory; a fresh clone without model weights cannot complete the build.

From the repository root:

```bash
docker build -t etsy-review-intelligence .
docker run --rm -p 7860:7860 --env-file .env etsy-review-intelligence
```

Open http://localhost:7860. The image builds the frontend, installs Python dependencies and NLTK stopwords, downloads the topic embedding model, and starts `backend.app:app` as a non-root user.

The build context excludes local environments, tests, notebooks, and generated reports. The production sentiment model is included; baseline and checkpoint directories are excluded.

## Hugging Face Docker Space

Use the root Dockerfile as the deployment artifact, with the Space configured for the Docker SDK and application port `7860`. Supply the exported sentiment model in the deployment context; pushing only the tracked files from this repository does not include it.

Configure `ETSY_API_KEY` and `ETSY_API_SECRET` as deployment secrets. `ETSY_API_BASE_URL` is optional and defaults to `https://openapi.etsy.com/v3`. Do not copy a local `.env` into the image.

## Operational behavior

- JSON reports are written to `/app/data`. Container-local reports are lost when the container is removed unless this directory is backed by persistent storage. A mounted directory must be writable by UID 1000.
- The analysis cache is in memory, holds eight entries per process, and is cleared on restart. Reviews are still fetched before a cache lookup.
- Analysis is synchronous. The cache lock serializes expensive analyses within a process, and a multi-listing request processes listings sequentially.
- Report endpoints have no authentication. Use access controls before exposing collected review reports on a shared service.
- `/api/health` confirms service liveness only. It does not prove that Etsy credentials, model artifacts, or external services are available.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Fine-tuned model not found | Restore the full model/tokenizer export under `models/distilbert-amazon-reviews/final/`. |
| Missing NLTK stopwords | Run `python -m nltk.downloader stopwords` in the active environment. |
| Frontend is not built | Run `npm ci` and `npm run build` in `frontend/`, then restart the backend. |
| Etsy request fails | Check configured credentials, listing availability, network connectivity, and the returned API error. |
| Slow first analysis | The embedding model loads on first use and may need to download; CPU inference and clustering also take time. |

Development and deployment use the same root `backend/`, `frontend/`, and `Dockerfile`. No separate deployment copy is needed.

The previous deployment checkout targeted `https://huggingface.co/spaces/Khdidij/etsy-review-intelligence`. Its Space metadata is preserved below for use in the deployment README:

```yaml
---
title: Etsy Review Intelligence
emoji: 🛍️
colorFrom: yellow
colorTo: yellow
sdk: docker
app_port: 7860
fullWidth: true
short_description: AI sentiment and topic analysis for Etsy reviews
---
```

When publishing model weights to a Git-based deployment repository, configure Git LFS for `*.safetensors` and `*.bin`. The main repository intentionally ignores `models/`; model artifacts must be supplied separately for deployment.
