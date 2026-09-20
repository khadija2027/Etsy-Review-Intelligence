"""Bounded reuse of analysis for identical, freshly fetched reviews."""
import hashlib
import json
from collections import OrderedDict
from copy import deepcopy
from threading import Lock

from .sentiment_analysis import ANALYSIS_VERSION, analyse_reviews

_cache = OrderedDict()
_lock = Lock()
_MAX_ENTRIES = 8


def analyse_cached(reviews):
    encoded = json.dumps(reviews, ensure_ascii=False, sort_keys=True).encode("utf-8")
    key = (ANALYSIS_VERSION, hashlib.sha256(encoded).hexdigest())
    # Serialize expensive analyses to avoid CPU oversubscription and duplicate work.
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            result, annotations = deepcopy(_cache[key])
            for review, annotation in zip(reviews, annotations):
                review.update(annotation)
            return result, True
        result = analyse_reviews(reviews)
        # analyse_reviews also annotates its input; callers need those scores
        # for review-level charts, even when the aggregate result is cached.
        annotations = [{"sentiment": review["sentiment"]} if "sentiment" in review else {} for review in reviews]
        _cache[key] = deepcopy((result, annotations))
        if len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)
        return result, False
