"""Review intelligence built on transformer sentiment and HDBSCAN topic discovery."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np

MODEL_NAME = "distilbert-amazon-reviews-finetuned"
MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "distilbert-amazon-reviews" / "final"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ANALYSIS_VERSION = 6
GENERIC_CLUSTER_WORDS = frozenset({"love", "great", "good", "perfect", "amazing", "beautiful", "thank", "thanks", "recommend", "item", "product", "order", "seller"})


@lru_cache(maxsize=1)
def _sentiment_pipeline():
    from transformers import pipeline
    if not (MODEL_DIR / "config.json").is_file():
        raise FileNotFoundError(
            f"Fine-tuned sentiment model not found at '{MODEL_DIR}'. "
            "Run fine_tune_distilbert_amazon_reviews.ipynb to create it."
        )
    return pipeline("sentiment-analysis", model=str(MODEL_DIR), tokenizer=str(MODEL_DIR))


@lru_cache(maxsize=1)
def _embedder():
    """Load the compact semantic model once, on the first clustering run."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Semantic topic clustering needs sentence-transformers and hdbscan. "
            "Run `pip install -r requirements.txt`."
        ) from exc
    return SentenceTransformer(EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _stop_words() -> frozenset[str]:
    """Load NLTK's built-in stop words for every supported review language."""
    try:
        from nltk.corpus import stopwords

        languages = stopwords.fileids()
        return frozenset(
            word.casefold()
            for language in languages
            for word in stopwords.words(language)
            if word.strip()
        )
    except LookupError as exc:
        raise RuntimeError(
            "NLTK stop words are not installed. Run `python -c "
            "\"import nltk; nltk.download('stopwords')\"` once."
        ) from exc


def _date_key(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|[\n\r]+", text) if part.strip()]


def _tokens(text: str) -> set[str]:
    return {
        word.casefold()
        for word in re.findall(r"[^\W\d_][^\W\d_'-]{2,}", text, flags=re.UNICODE)
        if word.casefold() not in _stop_words()
    }


def _score_predictions(texts: list[str]) -> list[dict[str, Any]]:
    if not texts:
        return []
    try:
        outputs = _sentiment_pipeline()([text[:512] for text in texts], batch_size=16, truncation=True)
    except Exception as exc:
        raise RuntimeError(f"Unable to load sentiment model '{MODEL_NAME}': {exc}") from exc
    scored = []
    for output in outputs:
        confidence = float(output["score"])
        positive = confidence if str(output["label"]).lower() == "positive" else 1 - confidence
        score = round((positive * 2) - 1, 4)
        # SST-2 has no neutral class, so low-confidence results are made explicit.
        scored.append({"label": "positive" if score >= .2 else "negative" if score <= -.2 else "neutral", "score": score})
    return scored


def _key_phrases(texts: Iterable[str], scores: Iterable[float], limit: int = 30) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    values: dict[str, list[float]] = defaultdict(list)
    for text, score in zip(texts, scores):
        words = [
            word.casefold()
            for word in re.findall(r"[^\W\d_][^\W\d_'-]{2,}", text, flags=re.UNICODE)
            if word.casefold() not in _stop_words()
        ]
        phrases = set(words)
        phrases.update(" ".join(pair) for pair in zip(words, words[1:]))
        for phrase in phrases:
            if phrase in GENERIC_CLUSTER_WORDS or len(phrase) < 4:
                continue
            counts[phrase] += 1
            values[phrase].append(float(score))
    return [{"phrase": phrase, "mentions": count, "average_sentiment": round(sum(values[phrase]) / count, 3)} for phrase, count in counts.most_common(limit)]


def _reduce_dimensions(embeddings: np.ndarray) -> np.ndarray:
    """Use UMAP before density clustering; retain a deterministic PCA fallback."""
    n_samples = len(embeddings)
    n_components = min(8, max(2, n_samples - 2))
    try:
        from umap import UMAP

        return UMAP(
            n_components=n_components,
            n_neighbors=max(2, min(15, n_samples - 1)),
            min_dist=0.0,
            metric="cosine",
            random_state=42,
        ).fit_transform(embeddings)
    except ImportError:
        from sklearn.decomposition import PCA

        return PCA(n_components=n_components, random_state=42).fit_transform(embeddings)


def _project_2d(embeddings: np.ndarray) -> np.ndarray:
    """Project sentence embeddings onto two dimensions for the intertopic distance map."""
    n_samples = len(embeddings)
    try:
        from umap import UMAP

        return UMAP(
            n_components=2,
            n_neighbors=max(2, min(15, n_samples - 1)),
            min_dist=0.1,
            metric="cosine",
            random_state=42,
        ).fit_transform(embeddings)
    except ImportError:
        from sklearn.decomposition import PCA

        return PCA(n_components=2, random_state=42).fit_transform(embeddings)


def _cluster_quality(embeddings: np.ndarray, labels: np.ndarray) -> dict[str, float | int | None]:
    """Return density-aware DBCV plus familiar silhouette and noise diagnostics."""
    non_noise = labels != -1
    cluster_count = len(set(labels[non_noise]))
    quality: dict[str, float | int | None] = {
        "dbcv": None,
        "silhouette": None,
        "n_clusters": cluster_count,
        "noise_ratio": round(float((labels == -1).sum()) / len(labels), 3),
    }
    if cluster_count < 2:
        return quality
    try:
        from hdbscan.validity import validity_index

        quality["dbcv"] = round(float(validity_index(embeddings.astype(np.float64), labels)), 3)
    except Exception:
        pass
    try:
        from sklearn.metrics import silhouette_score

        quality["silhouette"] = round(float(silhouette_score(embeddings[non_noise], labels[non_noise])), 3)
    except Exception:
        pass
    return quality


def _embedding_labels(
    sentences: list[str],
    labels: np.ndarray,
    embeddings: np.ndarray,
    sentence_languages: list[str] | None = None,
    top_n: int = 4,
) -> dict[int, list[str]]:
    """Label clusters with English phrases closest to each semantic centroid."""
    cluster_ids = sorted({int(label) for label in labels if label != -1})
    if not cluster_ids:
        return {}
    result: dict[int, list[str]] = {}
    for cluster_id in cluster_ids:
        cluster_indices = [index for index, label in enumerate(labels) if label == cluster_id]
        english_indices = [
            index
            for index in cluster_indices
            if sentence_languages is None
            or sentence_languages[index].casefold().split("-")[0] == "en"
        ]
        label_indices = english_indices or []
        candidate_phrases = set()
        for index in label_indices:
            words = [
                word.lower()
                for word in re.findall(r"[^\W\d_][^\W\d_'-]{2,}", sentences[index], flags=re.UNICODE)
                if word.casefold() not in _stop_words()
            ]
            candidate_phrases.update(words)
            candidate_phrases.update(" ".join(pair) for pair in zip(words, words[1:]))
        if not candidate_phrases:
            result[cluster_id] = ["multilingual topic"]
            continue
        phrases = sorted(candidate_phrases)
        phrase_embeddings = _embedder().encode(phrases, normalize_embeddings=True, show_progress_bar=False)
        centroid = embeddings[cluster_indices].mean(axis=0)
        centroid /= max(float(np.linalg.norm(centroid)), 1e-12)
        scores = phrase_embeddings @ centroid
        ranked = [
            phrase
            for phrase in (phrases[index] for index in np.argsort(scores)[::-1])
            if phrase not in GENERIC_CLUSTER_WORDS
        ]
        result[cluster_id] = ranked[:top_n] or ["multilingual topic"]
    return result


def _canonical_cluster_label(keywords: list[str], sentiment: float) -> str:
    """Turn ranked fragments into one readable business finding."""
    text = " ".join(keywords).casefold()
    if "apron" in text or "smock" in text:
        return "Loved the apron" if sentiment >= 0.2 else "Apron experience"
    if "purchase" in text or "bought" in text:
        return "Happy with purchase" if sentiment >= 0.2 else "Purchase concerns"
    if any(word in text for word in ("shipping", "shipped", "arrived", "delivery", "quickly", "fast")):
        return "Fast shipping" if sentiment >= 0.2 else "Shipping experience"
    if any(word in text for word in ("quality", "fabric", "material", "cotton", "workmanship")):
        return "High product quality" if sentiment >= 0.2 else "Product quality concerns"
    if any(word in text for word in ("fit", "fits", "size", "sizing", "comfortable")):
        return "Fit and sizing" if sentiment >= 0.2 else "Fit and sizing concerns"
    if any(word in text for word in ("color", "colors", "colour", "pictured", "appearance")):
        return "Color and appearance"
    if any(word in text for word in ("gift", "daughter", "friend")):
        return "Gift-worthy product" if sentiment >= 0.2 else "Gift experience"
    phrase = next((phrase for phrase in keywords if phrase), "customer experience")
    return phrase.replace("/", " ").strip().capitalize()


def _cluster_confidence(cluster_indices: list[int], embeddings: np.ndarray) -> float:
    """Score cluster compactness relative to the full sentence-embedding space."""
    if len(cluster_indices) < 3:
        return 0.0
    cluster_vectors = embeddings[cluster_indices]
    centroid = cluster_vectors.mean(axis=0)
    intra_distance = float(np.linalg.norm(cluster_vectors - centroid, axis=1).mean())
    overall_distance = float(np.linalg.norm(embeddings - centroid, axis=1).mean())
    return round(max(0.0, min(1.0, 1 - intra_distance / (overall_distance + 1e-8))), 2)


def _merge_similar_clusters(labels: np.ndarray, embeddings: np.ndarray, threshold: float = 0.86) -> np.ndarray:
    """Merge HDBSCAN clusters whose original embedding centroids are near-identical."""
    cluster_ids = sorted(int(label) for label in set(labels) if label != -1)
    if len(cluster_ids) < 2:
        return labels
    parents = {cluster_id: cluster_id for cluster_id in cluster_ids}

    def find(cluster_id: int) -> int:
        while parents[cluster_id] != cluster_id:
            parents[cluster_id] = parents[parents[cluster_id]]
            cluster_id = parents[cluster_id]
        return cluster_id

    centroids = {
        cluster_id: embeddings[labels == cluster_id].mean(axis=0)
        for cluster_id in cluster_ids
    }
    for cluster_id in cluster_ids:
        first = centroids[cluster_id]
        first /= max(float(np.linalg.norm(first)), 1e-12)
        for other_id in cluster_ids:
            if other_id <= cluster_id:
                continue
            second = centroids[other_id]
            second /= max(float(np.linalg.norm(second)), 1e-12)
            if float(first @ second) >= threshold:
                parents[find(other_id)] = find(cluster_id)

    merged = labels.copy()
    roots = {cluster_id: find(cluster_id) for cluster_id in cluster_ids}
    compact_ids = {root: index for index, root in enumerate(sorted(set(roots.values())))}
    for cluster_id, root in roots.items():
        merged[labels == cluster_id] = compact_ids[root]
    return merged


def _semantic_cluster_analysis(
    texts: list[str],
    scores: list[float],
    languages: list[str] | None = None,
    review_dates: list[Any] | None = None,
) -> dict[str, Any]:
    """Discover recurring review topics with sentence embeddings, UMAP, and HDBSCAN."""
    try:
        from hdbscan import HDBSCAN
    except ImportError as exc:
        raise RuntimeError("Semantic topic clustering needs hdbscan. Run `pip install -r requirements.txt`.") from exc

    # Short sentences typically contain one customer issue more clearly than full reviews.
    items = [
        (review_index, sentence)
        for review_index, text in enumerate(texts)
        for sentence in _sentences(text)
        if len(_tokens(sentence)) >= 3
    ]
    if len(items) < 4:
        return {
            "clusters": [],
            "quality": None,
            "intertopic_map": {},
            "metadata": {
                "total_sentences": len(items),
                "label_method": "multilingual clustering with English semantic labels",
                "analysis_version": ANALYSIS_VERSION,
            },
        }

    sentences = [sentence for _, sentence in items]
    sentence_languages = [
        languages[review_index] if languages and review_index < len(languages) else ""
        for review_index, _ in items
    ]
    embeddings = _embedder().encode(sentences, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
    reduced_embeddings = _reduce_dimensions(embeddings)
    min_cluster_size = max(2, min(6, len(items) // 8))
    labels = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=max(1, min_cluster_size // 2),
        metric="euclidean",
        cluster_selection_method="eom",
    ).fit_predict(reduced_embeddings)
    labels = _merge_similar_clusters(labels, embeddings)
    quality = _cluster_quality(reduced_embeddings, labels)
    cluster_labels = _embedding_labels(sentences, labels, embeddings, sentence_languages)

    groups: dict[int, list[int]] = defaultdict(list)
    for sentence_index, cluster_id in enumerate(labels):
        if cluster_id != -1:  # HDBSCAN labels outliers as -1 instead of forcing a topic.
            groups[int(cluster_id)].append(sentence_index)

    clusters = []
    cluster_sentiments: dict[int, float] = {}
    for cluster_id, sentence_indices in groups.items():
        if len(sentence_indices) < 2:
            continue
        review_indices = sorted({items[index][0] for index in sentence_indices})
        centroid = embeddings[sentence_indices].mean(axis=0)
        centroid /= max(float(np.linalg.norm(centroid)), 1e-12)
        representative_index = max(sentence_indices, key=lambda index: float(embeddings[index] @ centroid))
        keywords = cluster_labels.get(cluster_id, ["customer experience"])
        average_sentiment = round(sum(scores[index] for index in review_indices) / len(review_indices), 3)
        canonical_label = _canonical_cluster_label(keywords, average_sentiment)
        sentiment_breakdown = {
            "positive": sum(scores[index] >= 0.2 for index in review_indices),
            "neutral": sum(-0.2 < scores[index] < 0.2 for index in review_indices),
            "negative": sum(scores[index] <= -0.2 for index in review_indices),
        }
        date_counts: Counter[str] = Counter()
        if review_dates:
            for review_index in review_indices:
                if date := _date_key(review_dates[review_index]):
                    date_counts[date] += 1
        cluster_sentiments[cluster_id] = average_sentiment
        clusters.append({
            # Dashboard fields.
            "theme": canonical_label,
            "reviews": len(review_indices),
            "average_sentiment": average_sentiment,
            "sample_review": items[representative_index][1][:240],
            "method": "multilingual sentence-transformers + UMAP + HDBSCAN + English semantic labels",
            # Explainable clustering fields.
            "primary_theme": canonical_label,
            "all_keywords": keywords,
            "confidence": _cluster_confidence(sentence_indices, embeddings),
            "representative_full_review": texts[items[representative_index][0]][:500],
            "cluster_id": cluster_id,
            "sentence_count": len(sentence_indices),
            "sentiment_breakdown": sentiment_breakdown,
            "date_counts": dict(sorted(date_counts.items())),
        })
    clusters.sort(key=lambda item: (-item["reviews"], item["average_sentiment"]))

    # Intertopic Distance Map payload: every sentence as a 2-D point plus a
    # larger labelled centroid per topic, mirroring BERTopic's signature visual.
    intertopic_map: dict[str, Any] = {}
    try:
        projected = _project_2d(embeddings)
        points = [
            {"x": round(float(x), 3), "y": round(float(y), 3), "t": int(label)}
            for (x, y), label in zip(projected, labels)
        ]
        centroids = []
        for cluster_id, sentence_indices in sorted(groups.items()):
            if len(sentence_indices) < 2:
                continue
            centroids.append({
                "t": cluster_id,
                "x": round(float(np.mean([projected[index, 0] for index in sentence_indices])), 3),
                "y": round(float(np.mean([projected[index, 1] for index in sentence_indices])), 3),
                "label": _canonical_cluster_label(cluster_labels.get(cluster_id, ["customer experience"]), cluster_sentiments.get(cluster_id, 0.0)),
                "size": len(sentence_indices),
                "sentiment": cluster_sentiments.get(cluster_id, 0.0),
            })
        intertopic_map = {"points": points, "centroids": centroids}
    except Exception:
        intertopic_map = {}

    return {
        "clusters": clusters[:8],
        "quality": quality,
        "intertopic_map": intertopic_map,
        "metadata": {
            "total_sentences": len(sentences),
            "total_clusters_found": len(clusters),
            "min_cluster_size_used": min_cluster_size,
            "label_method": "multilingual clustering with English semantic labels",
            "analysis_version": ANALYSIS_VERSION,
        },
    }


def _business_insights(clusters: list[dict[str, Any]], total: int) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    for issue in sorted((item for item in clusters if item["average_sentiment"] < 0), key=lambda item: item["average_sentiment"])[:3]:
        insights.append({"type": "priority", "text": f"Prioritise “{issue['theme']}”: {issue['reviews']} reviews share this recurring concern (average sentiment {issue['average_sentiment']:+.2f})."})
    strengths = [item for item in clusters if item["average_sentiment"] >= .35]
    if strengths:
        best = max(strengths, key=lambda item: (item["reviews"], item["average_sentiment"]))
        insights.append({"type": "strength", "text": f"Protect “{best['theme']}”; customers consistently praise it ({best['reviews']} reviews, {best['average_sentiment']:+.2f} sentiment)."})
    if not insights and total:
        insights.append({"type": "watch", "text": "No material negative topic cluster was detected. Track future review volume before drawing strong conclusions."})
    return insights


def analyse_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Annotate reviews and return presentation-ready KPIs plus HDBSCAN topic clusters."""
    texts = [str(review.get("review_text") or "").strip() for review in reviews]
    non_empty = [(index, text) for index, text in enumerate(texts) if text]
    predictions = {index: score for (index, _), score in zip(non_empty, _score_predictions([text for _, text in non_empty]))}

    ratings: list[float] = []
    scores: list[float] = []
    trend: dict[str, list[float]] = defaultdict(list)
    counts = Counter()
    mismatches = 0
    for index, review in enumerate(reviews):
        try:
            rating = float(review.get("rating"))
        except (TypeError, ValueError):
            rating = None
        if rating is not None:
            ratings.append(rating)
        sentiment = predictions.get(index, {"label": "neutral", "score": 0.0})
        score, label = float(sentiment["score"]), str(sentiment["label"])
        review["sentiment"] = {**sentiment, "model": MODEL_NAME if index in predictions else None}
        scores.append(score)
        counts[label] += 1
        if rating is not None and ((rating >= 4 and score < -.2) or (rating <= 2 and score > .2)):
            mismatches += 1
        if date := _date_key(review.get("review_date")):
            trend[date].append(score)

    total = len(reviews)
    languages = [str(review.get("language") or "") for review in reviews]
    review_dates = [review.get("review_date") for review in reviews]
    semantic_clusters = _semantic_cluster_analysis(texts, scores, languages, review_dates)
    clusters = semantic_clusters["clusters"]
    sentiment_average = sum(scores) / total if total else 0
    return {
        "model": MODEL_NAME, "total_reviews": total,
        "average_star_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "positive_sentiment_percent": round(counts["positive"] / total * 100, 1) if total else 0,
        "negative_sentiment_percent": round(counts["negative"] / total * 100, 1) if total else 0,
        "neutral_sentiment_percent": round(counts["neutral"] / total * 100, 1) if total else 0,
        "average_sentiment_score": round(sentiment_average, 3),
        "rating_text_mismatch_percent": round(mismatches / total * 100, 1) if total else 0,
        "sentiment_trend": [{"date": date, "average_score": round(sum(values) / len(values), 3), "reviews": len(values)} for date, values in sorted(trend.items())],
        "key_phrases": _key_phrases(texts, scores),
        "review_clusters": clusters,
        "cluster_quality": semantic_clusters["quality"],
        "intertopic_map": semantic_clusters.get("intertopic_map") or {},
        "cluster_metadata": semantic_clusters["metadata"],
        "business_insights": _business_insights(clusters, total),
        "methodology": "Overall sentiment uses the fine-tuned DistilBERT model. Recurring review topics use multilingual Sentence-Transformers embeddings, UMAP reduction, HDBSCAN density clustering, and embedding-based phrase labels. DBCV, silhouette, and noise ratio are reported when enough clusters are found.",
    }


def compare_listing_satisfaction(listings: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a comparable customer-satisfaction view for analysed listings."""
    rows: list[dict[str, Any]] = []
    phrase_totals: dict[str, dict[str, float]] = {}
    topic_overview: list[dict[str, Any]] = []
    product_views: list[dict[str, Any]] = []
    map_points: list[dict[str, Any]] = []
    map_centroids: list[dict[str, Any]] = []
    map_topic_id = 0
    for listing in listings:
        kpi = listing["sentiment_analysis"]
        listing_id = str(listing["listing_id"])
        listing_title = listing.get("listing_title") or f"Listing {listing_id}"
        rating = kpi.get("average_star_rating")
        satisfaction = round(((float(kpi["average_sentiment_score"]) + 1) / 2) * 60 + ((float(rating) / 5) if rating is not None else .5) * 40, 1)
        rows.append({
            "listing_id": listing_id,
            "listing_title": listing_title,
            "reviews": kpi["total_reviews"],
            "average_star_rating": rating,
            "positive_sentiment_percent": kpi["positive_sentiment_percent"],
            "negative_sentiment_percent": kpi["negative_sentiment_percent"],
            "neutral_sentiment_percent": kpi["neutral_sentiment_percent"],
            "average_sentiment_score": kpi["average_sentiment_score"],
            "rating_text_mismatch_percent": kpi["rating_text_mismatch_percent"],
            "topic_count": len(kpi.get("review_clusters") or []),
            "satisfaction_score": satisfaction,
        })
        product_views.append({
            "listing_id": listing_id,
            "listing_title": listing_title,
            "key_phrases": (kpi.get("key_phrases") or [])[:30],
            "review_clusters": (kpi.get("review_clusters") or [])[:12],
        })
        for phrase in kpi.get("key_phrases") or []:
            entry = phrase_totals.setdefault(phrase["phrase"], {"mentions": 0, "sentiment_total": 0})
            entry["mentions"] += int(phrase.get("mentions") or 0)
            entry["sentiment_total"] += float(phrase.get("average_sentiment") or 0) * int(phrase.get("mentions") or 0)
        for topic in kpi.get("review_clusters") or []:
            topic_overview.append({
                "theme": topic.get("theme") or "Customer experience",
                "listing_title": listing_title,
                "reviews": topic.get("reviews", 0),
                "average_sentiment": topic.get("average_sentiment", 0),
                "sample_review": topic.get("sample_review", ""),
            })
        topic_map = kpi.get("intertopic_map") or {}
        points = topic_map.get("points") or []
        centroids = topic_map.get("centroids") or []
        if points or centroids:
            all_x = [float(point["x"]) for point in points] + [float(centroid["x"]) for centroid in centroids]
            all_y = [float(point["y"]) for point in points] + [float(centroid["y"]) for centroid in centroids]
            min_x, max_x = min(all_x), max(all_x)
            min_y, max_y = min(all_y), max(all_y)
            scale_x = max(max_x - min_x, 1e-9)
            scale_y = max(max_y - min_y, 1e-9)
            topic_ids = {}
            for centroid in centroids:
                topic_ids[centroid.get("t")] = map_topic_id
                map_topic_id += 1
            for point in points:
                map_points.append({
                    "x": round(((float(point["x"]) - min_x) / scale_x) * 2 - 1, 3),
                    "y": round(((float(point["y"]) - min_y) / scale_y) * 2 - 1, 3),
                    "t": topic_ids.get(point.get("t"), map_topic_id),
                })
            for centroid in centroids:
                map_centroids.append({
                    "t": topic_ids[centroid.get("t")],
                    "x": round(((float(centroid["x"]) - min_x) / scale_x) * 2 - 1, 3),
                    "y": round(((float(centroid["y"]) - min_y) / scale_y) * 2 - 1, 3),
                    "label": f"{listing_title}: {centroid.get('label', 'Topic')}",
                    "size": centroid.get("size", 0),
                    "sentiment": centroid.get("sentiment", 0),
                })
    rows.sort(key=lambda row: (-row["satisfaction_score"], -row["reviews"], row["listing_id"]))
    for rank, row in enumerate(rows, 1): row["rank"] = rank
    insights = [f"Highest satisfaction: {rows[0]['listing_title']} ({rows[0]['satisfaction_score']}/100)."] if rows else []
    if len(rows) > 1: insights.append(f"Most improvement opportunity: {rows[-1]['listing_title']} ({rows[-1]['satisfaction_score']}/100).")
    phrases = [
        {
            "phrase": phrase,
            "mentions": int(values["mentions"]),
            "average_sentiment": round(values["sentiment_total"] / values["mentions"], 3),
        }
        for phrase, values in phrase_totals.items()
        if values["mentions"] > 0
    ]
    phrases.sort(key=lambda item: (-item["mentions"], item["phrase"]))
    topic_overview.sort(key=lambda item: (-item["reviews"], item["theme"]))
    topic_names = [topic["theme"] for topic in topic_overview[:12]]
    topic_names = list(dict.fromkeys(topic_names))
    topic_heatmap = {
        "topics": topic_names,
        "products": [
            {
                "listing_title": product["listing_title"],
                "values": [
                    next((topic["reviews"] for topic in product["review_clusters"] if topic.get("theme") == theme), 0)
                    for theme in topic_names
                ],
            }
            for product in product_views
        ],
    }
    return {
        "listings": rows,
        "insights": insights,
        "product_views": product_views,
        "key_phrases": phrases[:40],
        "review_clusters": topic_overview[:20],
        "topic_heatmap": topic_heatmap,
        "intertopic_map": {"points": map_points, "centroids": map_centroids},
        "methodology": "Satisfaction score weights review-text sentiment at 60% and star rating at 40%. Topic, language, and map views combine the selected listings.",
    }
