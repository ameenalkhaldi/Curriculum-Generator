import json
import math
import pathlib
import re
from typing import Dict, Any, List, Optional

def normalize_slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\u0600-\u06FF\- ]+", "", s)  # keep arabic letters too
    s = s.replace(" ", "-")
    s = re.sub(r"-+", "-", s)
    return s

def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    if na == 0 or nb == 0: return 0.0
    return dot / (na * nb)

class MemoryStore:
    """
    Simple JSON-based vector index:
      { "items":[ {"id":..., "title":..., "slug":..., "module":..., "path":..., "vector":[...], "meta":{...}}, ... ] }
    """
    def __init__(self, index_path: pathlib.Path):
        self.index_path = index_path
        if index_path.exists():
            self.index = json.loads(index_path.read_text(encoding="utf-8"))
        else:
            self.index = {"items": []}

    def add_item(self, item_id: str, title: str, slug: str, module: str, path: str, vector: List[float], meta: Dict[str, Any]):
        self.index["items"].append({
            "id": item_id,
            "title": title,
            "slug": slug,
            "module": module,
            "path": path,
            "vector": vector,
            "meta": meta,
        })

    def save(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(self.index, ensure_ascii=False, indent=2), encoding="utf-8")

    def _search_once(self, query_vec: List[float], k: int) -> List[Dict[str, Any]]:
        scored = []
        for it in self.index.get("items", []):
            vec = it.get("vector") or []
            c = cosine(query_vec, vec)
            scored.append( (c, it) )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in scored[:k]]

    def search(self, queries: List[str], k: int = 5) -> List[Dict[str, Any]]:
        """
        Naive hybrid: title/slug keyword boost + vector similarity if available.
        If no vectors yet, falls back to simple keyword ranking.
        NOTE: For simplicity, vectorization is handled by caller.
        """
        # if there are no vectors at all, just return most recent k
        has_vec = any(len((it.get("vector") or [])) > 0 for it in self.index.get("items", []))
        if not has_vec:
            items = list(self.index.get("items", []))
            items.sort(key=lambda it: it.get("meta", {}).get("created_at", 0), reverse=True)
            return items[:k]

        # quick keyword prefilter
        kw = " ".join(queries).lower()
        pref = []
        others = []
        for it in self.index.get("items", []):
            hay = f"{it.get('title','')} {it.get('slug','')} {it.get('module','')}".lower()
            (pref if any(w in hay for w in kw.split()) else others).append(it)

        # crude rerank: prefer keyword matches then vector search against all
        # (vector search is performed in caller; here we don't have query_vec, so just return pref + others top k)
        # To keep consistent API, we just return keyword-prioritized recent items.
        pref.sort(key=lambda it: it.get("meta", {}).get("created_at", 0), reverse=True)
        others.sort(key=lambda it: it.get("meta", {}).get("created_at", 0), reverse=True)
        return (pref + others)[:k]
