"""Historial local de reportes (SQLite, sin servidor ni nube).

Cada reporte guarda: pozo, fecha, lapso, texto en español, texto en inglés,
hallazgos y completitud. Sirve para reabrir el turno de ayer y para exportar.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.environ.get("RIGMIND_DB") or os.path.join(BASE_DIR, "data", "rigmind.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    well TEXT NOT NULL,
    report_date TEXT,
    period_start TEXT,
    period_end TEXT,
    spanish TEXT NOT NULL,
    english TEXT,
    findings_json TEXT,
    completeness INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at DESC);

CREATE TABLE IF NOT EXISTS well_state (
    well_key TEXT PRIMARY KEY,
    well TEXT NOT NULL,
    tubular TEXT,
    total_joints INTEGER,
    bha TEXT,
    last_depth_ft REAL,
    fluid TEXT,
    updated_at TEXT NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _db():
    """Conexión con commit y cierre garantizado (Windows bloquea el archivo si no se cierra)."""
    conn = _conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript(SCHEMA)


def save_report(data: Dict[str, Any]) -> int:
    init_db()
    findings = data.get("findings") or []
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO reports
               (well, report_date, period_start, period_end, spanish, english,
                findings_json, completeness, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                (data.get("well") or "Well").strip(),
                data.get("report_date") or datetime.now().strftime("%Y-%m-%d"),
                data.get("period_start") or "00:00",
                data.get("period_end") or "24:00",
                data.get("spanish") or "",
                data.get("english") or "",
                json.dumps(findings, ensure_ascii=False),
                int(data.get("completeness") or 0),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return int(cur.lastrowid)


def list_reports(limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    with _db() as conn:
        rows = conn.execute(
            """SELECT id, well, report_date, period_start, period_end,
                      completeness, created_at,
                      length(english) AS english_len, spanish
               FROM reports ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        excerpt = (r["spanish"] or "").strip().replace("\n", " ")
        out.append({
            "id": r["id"],
            "well": r["well"],
            "report_date": r["report_date"],
            "period_start": r["period_start"],
            "period_end": r["period_end"],
            "completeness": r["completeness"],
            "created_at": r["created_at"],
            "has_english": bool(r["english_len"]),
            "excerpt": excerpt[:120],
        })
    return out


def get_report(report_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with _db() as conn:
        r = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not r:
        return None
    try:
        findings = json.loads(r["findings_json"] or "[]")
    except Exception:
        findings = []
    return {
        "id": r["id"],
        "well": r["well"],
        "report_date": r["report_date"],
        "period_start": r["period_start"],
        "period_end": r["period_end"],
        "spanish": r["spanish"],
        "english": r["english"],
        "findings": findings,
        "completeness": r["completeness"],
        "created_at": r["created_at"],
    }


def update_report(report_id: int, data: Dict[str, Any]) -> bool:
    init_db()
    with _db() as conn:
        cur = conn.execute(
            """UPDATE reports SET spanish = ?, english = ?, findings_json = ?,
               completeness = ? WHERE id = ?""",
            (
                data.get("spanish") or "",
                data.get("english") or "",
                json.dumps(data.get("findings") or [], ensure_ascii=False),
                int(data.get("completeness") or 0),
                report_id,
            ),
        )
        return cur.rowcount > 0


def delete_report(report_id: int) -> bool:
    init_db()
    with _db() as conn:
        return conn.execute("DELETE FROM reports WHERE id = ?", (report_id,)).rowcount > 0


# ---------------------------------------------------------------------------
# Estado vivo del pozo (continuidad entre lapsos)
# ---------------------------------------------------------------------------
import re as _re


def _well_key(well: str) -> str:
    return _re.sub(r"[^a-z0-9]", "", (well or "").lower()) or "well"


def get_well_state(well: str) -> Optional[Dict[str, Any]]:
    init_db()
    wk = _well_key(well)
    with _db() as conn:
        r = conn.execute("SELECT * FROM well_state WHERE well_key = ?", (wk,)).fetchone()
    if not r:
        return None
    return {
        "well": r["well"],
        "tubular": r["tubular"],
        "total_joints": r["total_joints"],
        "bha": r["bha"],
        "last_depth_ft": r["last_depth_ft"],
        "fluid": r["fluid"],
        "updated_at": r["updated_at"],
    }


def upsert_well_state(well: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    wk = _well_key(well)
    cur = get_well_state(well) or {}
    merged = {
        "well": (well or cur.get("well") or "Well").strip(),
        "tubular": patch.get("tubular") or cur.get("tubular"),
        "total_joints": patch.get("total_joints") if patch.get("total_joints") is not None else cur.get("total_joints"),
        "bha": patch.get("bha") or cur.get("bha"),
        "last_depth_ft": patch.get("last_depth_ft") if patch.get("last_depth_ft") is not None else cur.get("last_depth_ft"),
        "fluid": patch.get("fluid") or cur.get("fluid"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _db() as conn:
        conn.execute(
            """INSERT INTO well_state
               (well_key, well, tubular, total_joints, bha, last_depth_ft, fluid, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(well_key) DO UPDATE SET
                   well = excluded.well,
                   tubular = excluded.tubular,
                   total_joints = excluded.total_joints,
                   bha = excluded.bha,
                   last_depth_ft = excluded.last_depth_ft,
                   fluid = excluded.fluid,
                   updated_at = excluded.updated_at""",
            (
                wk,
                merged["well"],
                merged["tubular"],
                merged["total_joints"],
                merged["bha"],
                merged["last_depth_ft"],
                merged["fluid"],
                merged["updated_at"],
            ),
        )
    return merged


def extract_well_state_from_text(text: str) -> Dict[str, Any]:
    """Extrae datos persistentes de un reporte (tubular, total de juntas, BHA, última cota, fluido)."""
    out: Dict[str, Any] = {}
    t = text or ""

    m_tub = _re.search(
        r'\b((?:tbg|tuber[ií]a|dp|drill\s*pipe)\s+\d+(?:[-\s]\d+/\d+)?\s*"?'
        r'(?:\s+(?:eu|eue|nue|if|vam|n-?80|l-?80|p-?110|j-?55))?'
        r'(?:\s+\d+(?:\.\d+)?\s*(?:lb/ft|#))?'
        r'(?:\s+(?:eu|eue|nue|n-?80|l-?80|p-?110|j-?55))?)',
        t,
        _re.IGNORECASE,
    )
    if m_tub and _re.search(r"lb/ft|#", m_tub.group(1), _re.IGNORECASE):
        out["tubular"] = _re.sub(r"\s+", " ", m_tub.group(1)).strip()

    m_jts = _re.search(r"\d+\s*/\s*(\d+)\s*(?:jtas?|juntas?|jts?)\b", t, _re.IGNORECASE)
    if m_jts:
        tot = int(m_jts.group(1))
        if tot > 0:
            out["total_joints"] = tot

    m_bha = _re.search(r"\b(BHA\s+No\.?\s*\d+[^.\n,;]{0,40})", t, _re.IGNORECASE)
    if m_bha:
        out["bha"] = _re.sub(r"\s+", " ", m_bha.group(1)).strip()

    depths = _re.findall(r"(?:hasta|@)\s*(\d{3,5}(?:\.\d+)?)\s*ft\b", t, _re.IGNORECASE)
    if depths:
        try:
            out["last_depth_ft"] = float(depths[-1])
        except ValueError:
            pass

    m_fl = _re.search(r"\b(\d+(?:\.\d+)?\s*ppg(?:\s+[a-z0-9áéíóúñ\-]+){0,2})", t, _re.IGNORECASE)
    if m_fl:
        out["fluid"] = _re.sub(r"\s+", " ", m_fl.group(1)).strip()

    return out
