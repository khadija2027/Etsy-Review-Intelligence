from __future__ import annotations

import json
import logging
from time import perf_counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .etsy_reviews_service import fetch_listing_reviews
from .analysis_cache import analyse_cached
from .sentiment_analysis import ANALYSIS_VERSION, analyse_reviews, compare_listing_satisfaction

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Etsy Review Intelligence API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    listing_ids: list[str] = Field(default_factory=list, max_length=10)


def _references(payload: AnalysisRequest) -> list[str]:
    references = list(dict.fromkeys(str(value).strip() for value in payload.listing_ids if str(value).strip()))
    if not references:
        raise HTTPException(status_code=400, detail="Provide one to ten Etsy listing IDs or URLs.")
    return references


def _save_report(result: dict[str, Any], prefix: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    result["saved_at"] = now.isoformat()
    filename = f"{prefix}_{now.strftime('%Y%m%d_%H%M%S')}.json"
    with (DATA_DIR / filename).open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    result["saved_file"] = filename
    return result


def _analyse_reference(reference: str) -> dict[str, Any]:
    started = perf_counter()
    listing = fetch_listing_reviews(reference)
    fetched = perf_counter()
    listing["sentiment_analysis"], cache_hit = analyse_cached(listing["reviews"])
    logging.getLogger("uvicorn.error").info(
        "Listing %s: fetch=%.2fs analysis=%.2fs cache_hit=%s reviews=%s",
        listing["listing_id"], fetched - started, perf_counter() - fetched,
        cache_hit, len(listing["reviews"]),
    )
    return listing


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "etsy-review-intelligence"}


@app.get("/api/reports")
def reports() -> dict[str, list[str]]:
    return {"reports": sorted((path.name for path in DATA_DIR.glob("*.json")), reverse=True)}


@app.get("/api/reports/{filename}")
def report(filename: str) -> dict[str, Any]:
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise HTTPException(status_code=404, detail="Report not found.")
    path = DATA_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found.")
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    try:
        if isinstance(payload.get("sentiment_analysis"), dict) and payload.get("reviews") is not None:
            kpi = payload["sentiment_analysis"]
            if (kpi.get("cluster_metadata") or {}).get("analysis_version") != ANALYSIS_VERSION or any(
                not isinstance(review.get("sentiment"), dict) or review["sentiment"].get("score") is None
                for review in payload["reviews"]
            ):
                payload["sentiment_analysis"] = analyse_reviews(payload["reviews"])
        elif payload.get("report_type") == "listing_comparison":
            changed = False
            for listing in payload.get("listings", []):
                kpi = listing.get("sentiment_analysis") or {}
                if (kpi.get("cluster_metadata") or {}).get("analysis_version") != ANALYSIS_VERSION or any(
                    not isinstance(review.get("sentiment"), dict) or review["sentiment"].get("score") is None
                    for review in listing.get("reviews") or []
                ):
                    listing["sentiment_analysis"] = analyse_reviews(listing.get("reviews") or [])
                    changed = True
            if changed:
                payload["comparison"] = compare_listing_satisfaction(payload["listings"])
        if payload.get("sentiment_analysis") or payload.get("comparison"):
            with path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return payload


@app.post("/api/analyze")
def analyze(payload: AnalysisRequest) -> dict[str, Any]:
    references = _references(payload)
    if len(references) == 1:
        try:
            result = _analyse_reference(references[0])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _save_report(result, result["listing_id"])

    successful: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for reference in references:
        try:
            successful.append(_analyse_reference(reference))
        except (ValueError, RuntimeError) as exc:
            failures.append({"listing_reference": reference, "error": str(exc)})
    if not successful:
        raise HTTPException(status_code=502, detail={"message": "No listings could be analysed.", "failures": failures})
    result = {
        "source": "etsy",
        "report_type": "listing_comparison",
        "listing_count": len(successful),
        "listings": successful,
        "failures": failures,
        "comparison": compare_listing_satisfaction(successful),
    }
    return _save_report(result, "comparison")


if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{path:path}")
def frontend(path: str = ""):
    if FRONTEND_DIST.is_dir():
        requested = FRONTEND_DIST / path
        if path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST / "index.html")
    return {"message": "Frontend is not built. Run `npm install` and `npm run build` in frontend/."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
