"""Memoria local de ejemplos aprobados por el usuario (append-only)."""

import json
import os
import re
from typing import Any, Dict, List, Optional

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "learning_memory.json")


def load_memory() -> List[Dict[str, Any]]:
    if not os.path.exists(MEMORY_FILE):
        return []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_to_memory(exemplar: Dict[str, Any]) -> bool:
    memory = load_memory()
    exemplar = dict(exemplar)
    exemplar["id"] = f"gold-{len(memory) + 1:03d}"
    memory.append(exemplar)
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9áéíóúñ]{3,}", (text or "").lower()))


def select_relevant_examples(
    text: str,
    ops: Optional[List[str]] = None,
    limit: int = 2,
) -> List[Dict[str, Any]]:
    """
    Devuelve hasta `limit` ejemplos aprobados ordenados por similitud léxica
    con el texto actual y coincidencia de operaciones detectadas.
    """
    memory = load_memory()
    if not memory or limit <= 0:
        return []
    query_toks = _tokens(text)
    op_toks = {o.lower().replace("_", " ") for o in (ops or [])}
    scored = []
    for item in memory:
        if not isinstance(item, dict):
            continue
        es = item.get("spanish_exemplar") or ""
        en = item.get("english_iadc") or ""
        op_name = item.get("operation") or ""
        if not es and not en:
            continue
        doc_toks = _tokens(f"{op_name} {es} {en}")
        overlap = len(query_toks & doc_toks)
        op_bonus = sum(3 for ot in op_toks if ot in op_name.lower() or ot in es.lower())
        score = overlap + op_bonus
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]
