"""
Cronología de un LAPSO de operación (no necesariamente 00:00-24:00).

El usuario pega el reporte de una operación que cubre un rango de horas
(ej. 07:00-24:00, o un turno de 06:00-14:00). Este módulo:

  - Extrae eventos con hora de inicio/fin explícita o modo secuencial.
  - Calcula duración por evento, cobertura real del lapso (unión de
    intervalos, no suma simple), huecos, solapes y eventos que cruzan
    medianoche.
  - Distingue "hueco dentro del reporte" (error) de "el reporte empieza
    después de las 00:00" (informativo, no error).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

INTERVAL_RE = re.compile(
    r"^\s*(?:de\s+)?(\d{1,2}:\d{2})\s*(?:-|–|—|a|al|to|hasta)\s*(\d{1,2}:\d{2})\s*"
    r"[:;,\-]?\s*(.*)$",
    re.IGNORECASE,
)
SINGLE_RE = re.compile(
    r"^\s*(?:de\s+)?(\d{1,2}:\d{2})\s*(?:h|hr|hrs|horas?)?\s*[:;,\-]?\s*(.*)$",
    re.IGNORECASE,
)
META_RE = re.compile(
    r"^\s*(pozo|well|campo|field|operadora|operator|contratista|contractor|"
    r"equipo|rig|taladro|fecha|date|d[ií]a|day|turno|shift|fluido|fluid)\s*[:=]\s*(.+)$",
    re.IGNORECASE,
)

MAX_MIN = 24 * 60


def hhmm_to_min(t: str) -> Optional[int]:
    m = re.match(r"^(\d{1,2}):(\d{2})$", (t or "").strip())
    if not m:
        return None
    h, mn = int(m.group(1)), int(m.group(2))
    if h == 24 and mn == 0:
        return MAX_MIN
    if h > 23 or mn > 59:
        return None
    return h * 60 + mn


def min_to_hhmm(m: int) -> str:
    m = m % MAX_MIN if m != MAX_MIN else MAX_MIN
    if m == MAX_MIN:
        return "24:00"
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass
class Event:
    idx: int
    start_min: int
    end_min: int
    text: str
    line_start: int
    line_end: int
    explicit: bool = True
    crosses_midnight: bool = False

    @property
    def start(self) -> str:
        return min_to_hhmm(self.start_min)

    @property
    def end(self) -> str:
        return min_to_hhmm(self.end_min)

    @property
    def duration_h(self) -> float:
        return round((self.end_min - self.start_min) / 60.0, 2)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.idx,
            "from": self.start,
            "to": self.end,
            "duration": self.duration_h,
            "description": self.text,
            "line": self.line_start,
            "explicit": self.explicit,
        }


@dataclass
class PeriodReport:
    events: List[Event] = field(default_factory=list)
    window_start: int = 0
    window_end: int = MAX_MIN
    meta: Dict[str, str] = field(default_factory=dict)
    issues: List[Dict[str, Any]] = field(default_factory=list)
    orphan_lines: List[Dict[str, Any]] = field(default_factory=list)

    # -- métricas ---------------------------------------------------------
    @property
    def documented_hours(self) -> float:
        return round(sum(e.duration_h for e in self.events), 2)

    def _merged_intervals(self) -> List[Tuple[int, int]]:
        iv = sorted((e.start_min, e.end_min) for e in self.events if e.end_min > e.start_min)
        merged: List[Tuple[int, int]] = []
        for s, t in iv:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], t))
            else:
                merged.append((s, t))
        return merged

    @property
    def covered_minutes(self) -> int:
        return sum(t - s for s, t in self._merged_intervals())

    @property
    def coverage_pct(self) -> float:
        total = max(1, self.window_end - self.window_start)
        return round(100.0 * self.covered_minutes / total, 1)

    @property
    def repeated_hours(self) -> float:
        """Horas contadas dos veces por intervalos solapados."""
        return round(max(0.0, self.documented_hours - self.covered_minutes / 60.0), 2)

    def gaps(self) -> List[Dict[str, Any]]:
        """Huecos sin registro dentro del lapso solicitado."""
        out: List[Dict[str, Any]] = []
        cursor = self.window_start
        for s, t in self._merged_intervals():
            if s > cursor:
                out.append({
                    "from": min_to_hhmm(cursor),
                    "to": min_to_hhmm(s),
                    "hours": round((s - cursor) / 60.0, 2),
                    "kind": "hueco",
                })
            cursor = max(cursor, t)
        if cursor < self.window_end:
            out.append({
                "from": min_to_hhmm(cursor),
                "to": min_to_hhmm(self.window_end),
                "hours": round((self.window_end - cursor) / 60.0, 2),
                "kind": "hueco",
            })
        return out

    def overlaps(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        ev = sorted(self.events, key=lambda e: e.start_min)
        for a, b in zip(ev, ev[1:]):
            if b.start_min < a.end_min:
                out.append({
                    "from": min_to_hhmm(b.start_min),
                    "to": min_to_hhmm(min(a.end_min, b.end_min)),
                    "hours": round((min(a.end_min, b.end_min) - b.start_min) / 60.0, 2),
                    "events": [a.idx, b.idx],
                })
        return out

    def as_dict(self) -> Dict[str, Any]:
        return {
            "window": {"from": min_to_hhmm(self.window_start), "to": min_to_hhmm(self.window_end)},
            "events": [e.as_dict() for e in self.events],
            "total_duration": self.documented_hours,
            "covered_hours": round(self.covered_minutes / 60.0, 2),
            "coverage_pct": self.coverage_pct,
            "repeated_hours": self.repeated_hours,
            "gaps": self.gaps(),
            "overlaps": self.overlaps(),
            "issues": self.issues,
            "meta": self.meta,
            "orphan_lines": self.orphan_lines,
            "mode": "secuencial" if any(not e.explicit for e in self.events) else "intervalos",
        }


def _parse_header(line: str, meta: Dict[str, str]) -> bool:
    m = META_RE.match(line)
    if m:
        meta[m.group(1).lower()] = m.group(2).strip()
        return True
    return False


def parse_period(
    text: str,
    window_start: str = "00:00",
    window_end: str = "24:00",
) -> PeriodReport:
    """Parsea el reporte y lo evalúa contra el lapso indicado por el usuario."""
    ws = hhmm_to_min(window_start) or 0
    we = hhmm_to_min(window_end) or MAX_MIN
    if we <= ws:
        we += MAX_MIN
    rep = PeriodReport(window_start=ws, window_end=we)

    lines = (text or "").replace("\r\n", "\n").split("\n")
    blocks: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if _parse_header(line, rep.meta):
            continue

        m_int = INTERVAL_RE.match(line)
        if m_int:
            current = {
                "start": m_int.group(1),
                "end": m_int.group(2),
                "text": m_int.group(3).strip(),
                "line_start": i,
                "line_end": i,
                "explicit": True,
            }
            blocks.append(current)
            continue

        m_single = SINGLE_RE.match(line)
        if m_single:
            current = {
                "start": m_single.group(1),
                "end": None,
                "text": m_single.group(2).strip(),
                "line_start": i,
                "line_end": i,
                "explicit": False,
            }
            blocks.append(current)
            continue

        if current is not None:
            current["text"] = (current["text"] + " " + line).strip()
            current["line_end"] = i
        else:
            rep.orphan_lines.append({"line": i + 1, "text": line})

    # -- convertir bloques a eventos --------------------------------------
    for idx, b in enumerate(blocks, start=1):
        s = hhmm_to_min(b["start"])
        if s is None:
            continue
        crosses = False
        if b["explicit"]:
            e = hhmm_to_min(b["end"])
            if e is None:
                continue
            if e < s:
                e += MAX_MIN
                crosses = True
        else:
            nxt = blocks[idx] if idx < len(blocks) else None
            if nxt is not None:
                e = hhmm_to_min(nxt["start"])
                if e is None:
                    e = s
                if e < s:
                    e += MAX_MIN
                    crosses = True
                elif e == s:
                    e = s
            else:
                # Sin siguiente evento: el fin es el fin del lapso (no se inventa una hora)
                e = rep.window_end if rep.window_end > s else s
        if e == s:
            rep.issues.append({
                "severity": "warning",
                "code": "duracion_cero",
                "message": f"El evento de las {b['start']} tiene duración 0: la hora de fin es igual a la de inicio.",
                "line": b["line_start"] + 1,
            })
        rep.events.append(Event(
            idx=idx, start_min=s, end_min=e, text=b["text"],
            line_start=b["line_start"], line_end=b["line_end"],
            explicit=b["explicit"], crosses_midnight=crosses,
        ))

    # -- detecciones -------------------------------------------------------
    for e in rep.events:
        if e.crosses_midnight:
            rep.issues.append({
                "severity": "info",
                "code": "cruza_medianoche",
                "message": f"El evento {e.start}-{e.end} cruza la medianoche; se contabilizó como {e.duration_h} h.",
                "line": e.line_start + 1,
            })
    for ov in rep.overlaps():
        rep.issues.append({
            "severity": "warning",
            "code": "solape",
            "message": f"Hay {ov['hours']} h de operaciones solapadas entre las {ov['from']} y las {ov['to']} "
                       f"(eventos {ov['events'][0]} y {ov['events'][1]}). Verifique si fueron simultáneas o error de hora.",
            "line": rep.events[ov["events"][1] - 1].line_start + 1 if ov["events"][1] - 1 < len(rep.events) else None,
        })
    for o in rep.orphan_lines:
        rep.issues.append({
            "severity": "warning",
            "code": "sin_hora",
            "message": f"Hay texto sin hora asignada: «{o['text'][:80]}». Todo evento del DOR debe tener su rango horario.",
            "line": o["line"],
        })
    if not rep.events:
        rep.issues.append({
            "severity": "critical",
            "code": "sin_eventos",
            "message": "No se detectó ningún evento con formato 'HH:MM - HH:MM: actividad'.",
            "line": None,
        })

    # Empieza después del inicio del lapso: informativo, no error
    if rep.events:
        first = min(e.start_min for e in rep.events)
        if first > rep.window_start:
            rep.issues.append({
                "severity": "info",
                "code": "inicio_tardio",
                "message": f"El reporte inicia a las {min_to_hhmm(first)} y el lapso analizado es "
                           f"{min_to_hhmm(rep.window_start)}-{min_to_hhmm(rep.window_end)}. "
                           f"Si el turno es parcial, ajuste 'Desde' para que la cobertura sea exacta.",
                "line": None,
            })
    return rep


def append_completion_markers(text: str, markers: Dict[int, List[str]]) -> str:
    """
    Agrega '[completar: ...]' al final de la línea del evento que tenga campos
    faltantes. `markers` = {id_evento: [campos faltantes]}.
    No toca eventos completos ni líneas que ya tengan un marcador.
    """
    if not markers:
        return text
    lines = text.replace("\r\n", "\n").split("\n")
    rep = parse_period(text)
    for ev in rep.events:
        fields = markers.get(ev.idx)
        if not fields:
            continue
        ln = ev.line_end
        if ln >= len(lines):
            continue
        if "[completar:" in lines[ln]:
            continue
        lines[ln] = lines[ln].rstrip() + f" [completar: {', '.join(fields)}]"
    return "\n".join(lines)
