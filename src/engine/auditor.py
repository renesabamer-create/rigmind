"""
Orquestador de auditoría para el flujo del asistente personal:

    reporte de un lapso  ->  auditoría (IA + reglas)  ->  texto corregido
    + hallazgos con evidencia + completitud por operación + sugerencias

Principios:
  - El texto del usuario NUNCA se inyecta crudo en HTML (se escapa).
  - Solo se corrige lo que se puede demostrar (aritmética, fechas inválidas,
    unidades absurdas, tipeo inequívoco). Lo demás se sugiere.
  - No se inventan fechas ni datos: se señalan y se proponen opciones.
  - Ningún hallazgo sin evidencia (línea + cita) cuando es verificable.
"""

import html
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from src.engine.completeness import evaluate as evaluate_completeness
from src.engine.period import append_completion_markers, parse_period
from src.engine.store import extract_well_state_from_text, get_well_state, upsert_well_state
from src.engine.text_rules import TYPO_RULES, VAGUE_PHRASES, spanish_residue

PROFILES_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "well_profiles.json")

SEV_ORDER = {"critical": 0, "warning": 1, "info": 2, "success": 3}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _line_of(text: str, needle: str) -> Optional[int]:
    if not needle:
        return None
    idx = text.find(needle)
    if idx < 0:
        return None
    return text.count("\n", 0, idx) + 1


def _quote(text: str, start: int, end: int, pad: int = 60) -> str:
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    return _norm(text[a:b])


def _finding(agent: str, severity: str, badge: str, message: str,
             evidence_line: Optional[int] = None, evidence_quote: Optional[str] = None,
             standard: Optional[str] = None, suggestion: Optional[str] = None,
             op: Optional[str] = None, autofix: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    return {
        "agent": agent,
        "severity": severity,
        "badge": badge,
        "message": message,
        "evidence": ({"line": evidence_line, "quote": evidence_quote}
                     if evidence_line or evidence_quote else None),
        "standard": standard,
        "suggestion": suggestion,
        "op": op,
        "autofix": autofix,
    }


def _find_iter_line(text: str, pattern: re.Pattern, group: int = 0) -> List[Tuple[re.Match, int]]:
    out = []
    for m in pattern.finditer(text):
        out.append((m, text.count("\n", 0, m.start(group)) + 1))
    return out


def load_well_profile(well_name: str) -> Optional[Dict[str, Any]]:
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            profiles = json.load(f)
    except Exception:
        return None
    key = re.sub(r"[^a-z0-9]", "", (well_name or "").lower())
    for name, prof in profiles.items():
        if re.sub(r"[^a-z0-9]", "", name.lower()) == key:
            return prof
    return None


# ---------------------------------------------------------------------------
# 1. Correcciones deterministas (solo lo demostrable)
# ---------------------------------------------------------------------------
def apply_typo_rules(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    findings: List[Dict[str, Any]] = []
    out = text
    for pattern, repl, label in TYPO_RULES:
        rx = re.compile(pattern, re.IGNORECASE)
        m = rx.search(out)
        if not m:
            continue
        before = m.group(0)
        after = m.expand(repl) if "\\" in repl else repl
        out = rx.sub(repl, out)
        findings.append(_finding(
            "oilfield-editor", "info", f"🔵 TIPEO: {label.upper()}",
            f"Se normalizó «{_norm(before)}» → «{_norm(after)}».",
            evidence_line=_line_of(text, before),
            evidence_quote=_norm(before),
            suggestion="Revise que el término normalizado corresponda a lo que ocurrió en campo.",
        ))
    return out, findings


# ---------------------------------------------------------------------------
# 2. Verificaciones numéricas con evidencia
# ---------------------------------------------------------------------------
def check_cement_thickness(text: str) -> List[Dict[str, Any]]:
    out = []
    rx = re.compile(
        r"(\d{3,5}(?:\.\d+)?)\s*ft\s*(?:a|hasta|-)\s*(\d{3,5}(?:\.\d+)?)\s*ft"
        r"[^.\n]{0,40}?(\d{1,4}(?:\.\d+)?)\s*ft\s*(?:de\s+)?espesor",
        re.IGNORECASE,
    )
    for m, line in _find_iter_line(text, rx):
        d1, d2, stated = float(m.group(1)), float(m.group(2)), float(m.group(3))
        calc = abs(d1 - d2)
        if abs(calc - stated) <= 1.0:
            out.append(_finding(
                "cementing", "success", "🟢 ESPESOR DE TAPÓN CONSISTENTE",
                f"{d1:.0f} ft − {d2:.0f} ft = {calc:.0f} ft; el reporte dice {stated:.0f} ft. Coincide.",
                evidence_line=line, evidence_quote=_norm(m.group(0)),
                standard="Aritmética de tapón (NORSOK D-010 / API RP 96)",
            ))
        else:
            out.append(_finding(
                "cementing", "critical", "🔴 ERROR ARITMÉTICO EN ESPESOR DE TAPÓN",
                f"{d1:.0f} ft − {d2:.0f} ft = {calc:.0f} ft de espesor, pero el reporte indica {stated:.0f} ft. "
                f"Diferencia: {abs(calc - stated):.0f} ft.",
                evidence_line=line, evidence_quote=_norm(m.group(0)),
                standard="Aritmética de tapón (NORSOK D-010 / API RP 96)",
                suggestion=f"Escriba «{d1:.0f} ft a {d2:.0f} ft, {calc:.0f} ft de espesor».",
                op="CEMENT_PLUG",
                autofix={"old": m.group(0), "new": m.group(0).replace(
                    f"{stated:.0f} ft de espesor", f"{calc:.0f} ft de espesor")},
            ))
    return out


def check_tally_progress(text: str) -> List[Dict[str, Any]]:
    out = []
    frac = re.compile(r"\(?\s*(\d+)\s*/\s*(\d+)\s*(?:jtas?|juntas?|jts?)\s*\)?", re.IGNORECASE)
    pct = re.compile(r"avance\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
    for m, line in _find_iter_line(text, frac):
        cur, tot = int(m.group(1)), int(m.group(2))
        if tot <= 0 or cur > tot:
            out.append(_finding(
                "tally", "critical", "🔴 FRACCIÓN DE JUNTAS IMPOSIBLE",
                f"La fracción ({cur}/{tot} jtas) no es válida: no se pueden sacar más juntas que el total de la sarta.",
                evidence_line=line, evidence_quote=_norm(m.group(0)),
                standard="Tally / IADC DOR",
                suggestion="Confirme el total de juntas de la sarta y el acumulado real.",
                op="POOH",
            ))
            continue
        calc = round(100 * cur / tot, 1)
        window = text[max(0, m.start() - 200): m.end() + 200]
        mp = pct.search(window)
        if mp:
            stated = float(mp.group(1))
            if abs(stated - calc) > 1.0:
                out.append(_finding(
                    "tally", "critical", "🔴 ERROR ARITMÉTICO EN AVANCE",
                    f"({cur}/{tot} jtas) = {calc}%, pero el reporte indica {stated}%. Diferencia: {abs(stated - calc):.1f} puntos.",
                    evidence_line=line, evidence_quote=_norm(m.group(0)),
                    standard="Tally / IADC DOR",
                    suggestion=f"Corrija a «avance: {calc}%».",
                    op="POOH",
                    autofix={"old": mp.group(0), "new": f"avance: {calc}%"},
                ))
            else:
                out.append(_finding(
                    "tally", "success", "🟢 AVANCE DE JUNTAS VERIFICADO",
                    f"({cur}/{tot} jtas) = {calc}% y el reporte indica {stated}%. Consistente.",
                    evidence_line=line, evidence_quote=_norm(m.group(0)),
                    standard="Tally / IADC DOR", op="POOH",
                ))
    return out


def check_rig_move(text: str) -> List[Dict[str, Any]]:
    out = []
    rx = re.compile(
        r"r/m\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%\s*[\(\[]?\s*(\d+)\s*/\s*(\d+)\s*(?:cargas?|loads)?",
        re.IGNORECASE,
    )
    for m, line in _find_iter_line(text, rx):
        stated, cur, tot = float(m.group(1)), int(m.group(2)), int(m.group(3))
        if tot <= 0:
            continue
        calc = round(100 * cur / tot, 1)
        if abs(stated - calc) > 1.0:
            out.append(_finding(
                "rig-move", "critical", "🔴 ERROR ARITMÉTICO EN R/M (CARGAS VS %)",
                f"{cur}/{tot} cargas = {calc}%, pero el reporte indica {stated}%.",
                evidence_line=line, evidence_quote=_norm(m.group(0)),
                standard="Contrato de movilización (lump sum / day rate)",
                suggestion=f"Corrija a «R/M: {calc}% ({cur}/{tot} cargas)».",
                op="RIG_MOVE",
                autofix={"old": m.group(0), "new": f"R/M: {calc}% ({cur}/{tot} cargas)"},
            ))
    return out


def check_units(text: str) -> List[Dict[str, Any]]:
    out = []
    rx = re.compile(r"\b(\d{4,6})\s*klbs?\b", re.IGNORECASE)
    for m, line in _find_iter_line(text, rx):
        val = int(m.group(1))
        if val < 1000:
            continue
        klb = round(val / 1000.0, 1)
        out.append(_finding(
            "tally", "critical", "🔴 UNIDAD IMPOSIBLE EN PESO",
            f"{val:,} klb equivale a {val/1000:.1f} millones de libras (1 klb = 1,000 lb). "
            f"Lo que se reportó en el indicador son {val:,} lb = {klb} klb.",
            evidence_line=line, evidence_quote=_norm(m.group(0)),
            standard="Unidades de campo (1 klb = 1,000 lb)",
            suggestion=f"Escriba «{klb:.1f} klb ({val:,} lb)».",
            autofix={"old": m.group(0), "new": f"{klb:g} klb ({val:,} lb)"},
        ))
    return out


def check_pressure_tests(text: str) -> List[Dict[str, Any]]:
    out = []
    low = re.compile(r"en\s+baja[^.\n]{0,40}?(\d{2,4})\s*psi(?:\s*[x×]\s*(\d+)\s*min)?", re.IGNORECASE)
    for m, line in _find_iter_line(text, low):
        psi = int(m.group(1))
        minutes = int(m.group(2)) if m.group(2) else None
        if not (250 <= psi <= 350):
            out.append(_finding(
                "bop", "critical" if psi > 400 else "warning", "🟠 PRUEBA EN BAJA FUERA DE RANGO",
                f"La prueba en baja se reportó a {psi} psi; API 53 exige 250-350 psi. "
                f"Un valor alto no detecta fugas de elastómeros; uno bajo no es representativo.",
                evidence_line=line, evidence_quote=_norm(m.group(0)),
                standard="API Standard 53 (prueba en baja 250-350 psi)",
                suggestion="Reporte la presión real de la prueba en baja dentro de 250-350 psi.",
                op="BOP_TEST",
            ))
        if minutes is not None and minutes < 5:
            out.append(_finding(
                "bop", "critical", "🔴 TIEMPO DE PRUEBA INSUFICIENTE",
                f"La prueba se sostuvo {minutes} min; el mínimo de estabilización es 5 min (10 recomendado).",
                evidence_line=line, evidence_quote=_norm(m.group(0)),
                standard="API Standard 53",
                suggestion="Registre el tiempo estabilizado real (mínimo 5 min).",
                op="BOP_TEST",
            ))
    return out


def check_dates(text: str) -> List[Dict[str, Any]]:
    out = []
    rx = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
    days_in_month = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    for m, line in _find_iter_line(text, rx):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        problem = None
        if not (1 <= mo <= 12):
            problem = f"el mes {mo} no existe"
        elif not (1 <= d <= days_in_month[mo]):
            problem = f"el mes {mo} tiene {days_in_month[mo]} días"
        if problem:
            out.append(_finding(
                "chrono", "critical", "🔴 FECHA INEXISTENTE",
                f"La fecha {m.group(0)} no existe: {problem}. No se corrige automáticamente porque "
                f"cambiar la fecha de un reporte altera el corte de facturación.",
                evidence_line=line, evidence_quote=_norm(m.group(0)),
                standard="Calendario / corte de facturación",
                suggestion="Confirme la fecha real con el taladro y corríjala manualmente.",
            ))
    return out


def check_sacks(text: str) -> List[Dict[str, Any]]:
    out = []
    rx = re.compile(
        r"(\d+(?:\.\d+)?)\s*bbl[^.\n]{0,60}?(\d+(?:\.\d+)?)\s*ppg[^.\n]{0,60}?(\d+(?:\.\d+)?)\s*(?:sx|sacos)",
        re.IGNORECASE,
    )
    for m, line in _find_iter_line(text, rx):
        bbl, ppg, sx = float(m.group(1)), float(m.group(2)), float(m.group(3))
        yield_cuft = 1.15 if abs(ppg - 15.8) <= 0.2 else None
        if not yield_cuft:
            continue
        expected = bbl * 5.615 / yield_cuft
        if abs(expected - sx) / expected > 0.08:
            out.append(_finding(
                "cementing", "warning", "🟠 SECTORES VS VOLUMEN DE LECHADA",
                f"Con {bbl} bbl de lechada a {ppg} ppg (rendimiento {yield_cuft} cu.ft/sx) se esperan "
                f"≈{expected:.0f} sx, pero el reporte indica {sx:.0f} sx.",
                evidence_line=line, evidence_quote=_norm(m.group(0)),
                standard="API Spec 10A (rendimiento de lechada)",
                suggestion="Verifique volumen bombeado o sacos despachados.",
                op="CEMENT_PLUG",
            ))
    return out


def check_vague(text: str) -> List[Dict[str, Any]]:
    out = []
    for pattern, suggestion in VAGUE_PHRASES:
        rx = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        for m, line in _find_iter_line(text, rx):
            out.append(_finding(
                "style", "warning", "🟠 FRASE SIN CONTENIDO TÉCNICO",
                f"«{_norm(m.group(0))}» no describe una maniobra verificable.",
                evidence_line=line, evidence_quote=_norm(m.group(0)),
                suggestion=suggestion,
            ))
            break  # una muestra por patrón para no saturar
    return out


def check_well_profile(text: str, well_name: str) -> List[Dict[str, Any]]:
    prof = load_well_profile(well_name)
    if not prof:
        return []
    out = []
    pbtd = prof.get("pbtd")
    if pbtd:
        depths = [float(x) for x in re.findall(r"(\d{3,5}(?:\.\d+)?)\s*ft", text)]
        if depths:
            dmax = max(depths)
            if dmax > float(pbtd) + 1:
                out.append(_finding(
                    "well", "warning", "🟠 PROFUNDIDAD MAYOR AL PBTD DEL POZO",
                    f"Se reporta {dmax:.0f} ft, pero el PBTD registrado para {well_name} es {pbtd:.0f} ft. "
                    f"Verifique la cota o el pozo.",
                    standard=f"Perfil de pozo {well_name}",
                    suggestion="Confirme si la profundidad es MD y si el PBTD está actualizado.",
                ))
    rating = prof.get("bop_rating") or ""
    m_rating = re.search(r"(\d[\d,]*)\s*psi", rating)
    if m_rating:
        rating_psi = int(m_rating.group(1).replace(",", ""))
        for m, line in _find_iter_line(text, re.compile(r"en\s+alta[^.\n]{0,30}?(\d{3,5})\s*psi", re.IGNORECASE)):
            tested = int(m.group(1))
            if tested > rating_psi:
                out.append(_finding(
                    "bop", "critical", "🔴 PRESIÓN DE PRUEBA SOBRE EL RATING DEL BOP",
                    f"Se probó a {tested} psi, pero el BOP de {well_name} es {rating} ({rating_psi} psi).",
                    evidence_line=line, evidence_quote=_norm(m.group(0)),
                    standard="API 16A / API 53",
                    suggestion="Corrija la presión de prueba o el rating del conjunto.",
                    op="BOP_TEST",
                ))
    return out


# ---------------------------------------------------------------------------
# 3. Diff visual escapado
# ---------------------------------------------------------------------------
def generate_diff_html(raw_text: str, corrected_text: str) -> str:
    import difflib
    raw_tok = re.findall(r"\S+|\n|[^\S\n]+", raw_text or "")
    cor_tok = re.findall(r"\S+|\n|[^\S\n]+", corrected_text or "")
    matcher = difflib.SequenceMatcher(None, raw_tok, cor_tok)
    out: List[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.append(html.escape("".join(raw_tok[i1:i2])))
            continue
        if tag in ("replace", "delete"):
            old = html.escape("".join(raw_tok[i1:i2]))
            out.append(f'<span class="diff-del"><s>{old}</s></span>')
        if tag in ("replace", "insert"):
            new = html.escape("".join(cor_tok[j1:j2]))
            if "[" in new and "]" in new:
                out.append(f'<span class="diff-blank"><b>{new}</b></span>')
            else:
                out.append(f'<span class="diff-ins"><b>{new}</b></span>')
    return "".join(out)


# ---------------------------------------------------------------------------
# 4. Normalización de hallazgos de IA
# ---------------------------------------------------------------------------
def _norm_ai_findings(items: Any) -> List[Dict[str, Any]]:
    out = []
    if not isinstance(items, list):
        return out
    for f in items:
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity", "info")).lower()
        if sev not in SEV_ORDER:
            sev = "info"
        ev = f.get("evidence") if isinstance(f.get("evidence"), dict) else None
        out.append(_finding(
            agent=str(f.get("agent", "ai-auditor")),
            severity=sev,
            badge=str(f.get("badge", "ℹ️ HALLAZGO")),
            message=str(f.get("message", "")).strip(),
            evidence_line=ev.get("line") if ev else f.get("line"),
            evidence_quote=ev.get("quote") if ev else None,
            standard=f.get("standard"),
            suggestion=f.get("suggestion"),
            op=f.get("op"),
        ))
    return out


# ---------------------------------------------------------------------------
# 5. Orquestador
# ---------------------------------------------------------------------------
def run_audit(
    raw_text: str,
    period_start: str = "00:00",
    period_end: str = "24:00",
    api_key: Optional[str] = None,
    provider: str = "auto",
    well_name: str = "Yopo-1",
    use_ai: bool = True,
    use_well_state: bool = False,
) -> Dict[str, Any]:
    raw_text = (raw_text or "").strip()
    findings: List[Dict[str, Any]] = []
    tips: List[str] = []

    period = parse_period(raw_text, period_start, period_end)

    # -- cronología -------------------------------------------------------
    for g in period.gaps():
        findings.append(_finding(
            "chrono", "warning" if g["hours"] >= 0.5 else "info", "🟠 HUECO EN LA CRONOLOGÍA",
            f"Hay {g['hours']} h sin registro entre las {g['from']} y las {g['to']}. "
            f"En un DOR, ese tiempo debe clasificarse como operación, standby o NPT.",
            suggestion="Agregue el evento faltante o clasifique el tiempo como standby/NPT.",
        ))
    for o in period.overlaps():
        findings.append(_finding(
            "chrono", "warning", "🟠 OPERACIONES SOLAPADAS",
            f"{o['hours']} h de solape entre las {o['from']} y las {o['to']}. "
            f"Si fueron simultáneas, indíquelo; si no, hay un error de hora.",
            suggestion="Corrija la hora de fin del primer evento o la de inicio del segundo.",
        ))
    for iss in period.issues:
        if iss["code"] in ("solape", "sin_hora", "duracion_cero", "cruza_medianoche", "inicio_tardio"):
            if iss["code"] == "solape":
                continue
            sev = {"warning": "warning", "info": "info", "critical": "critical"}.get(iss["severity"], "info")
            badge = {
                "sin_hora": "🟠 EVENTO SIN HORA",
                "duracion_cero": "🟠 DURACIÓN CERO",
                "cruza_medianoche": "🔵 CRUZA MEDIANOCHE",
                "inicio_tardio": "🔵 LAPSO PARCIAL",
                "sin_eventos": "🔴 SIN EVENTOS",
            }.get(iss["code"], "ℹ️ CRONOLOGÍA")
            findings.append(_finding("chrono", sev, badge, iss["message"],
                                     evidence_line=iss.get("line")))
    if period.events and period.coverage_pct >= 99.5:
        findings.append(_finding(
            "chrono", "success", "🟢 LAPSO CUBIERTO",
            f"Los {period.documented_hours} h del reporte cubren el {period.coverage_pct}% del lapso "
            f"{period.as_dict()['window']['from']}-{period.as_dict()['window']['to']}, sin huecos.",
        ))

    # -- IA (opcional) ----------------------------------------------------
    ai_status = {"connected": False, "provider": provider, "engine": "Reglas locales", "error": None}
    corrected = raw_text
    if use_ai and api_key and provider != "none":
        try:
            from src.engine.qaqc_auditor import call_ai_spanish_audit
            ai_res = call_ai_spanish_audit(raw_text, api_key=api_key, provider=provider, well_name=well_name)
            if ai_res and isinstance(ai_res.get("corrected_spanish"), str) and ai_res["corrected_spanish"].strip():
                corrected = ai_res["corrected_spanish"].strip()
                findings.extend(_norm_ai_findings(ai_res.get("agent_findings")))
                tips.extend([str(t) for t in (ai_res.get("learning_tips") or []) if str(t).strip()])
                ai_status = {"connected": True, "provider": provider,
                             "engine": f"{provider.capitalize()} (IA)", "error": None}
            else:
                ai_status = {"connected": False, "provider": provider, "engine": "Reglas locales",
                             "error": f"El proveedor '{provider}' no devolvió un texto válido."}
        except Exception as e:
            ai_status = {"connected": False, "provider": provider, "engine": "Reglas locales",
                         "error": str(e)}
            findings.append(_finding(
                "ai", "warning", "🟠 IA NO DISPONIBLE",
                f"No se pudo usar {provider.upper()}: {str(e)[:200]}. Se auditó con las reglas locales; "
                f"revise el texto con más cuidado.",
                suggestion="Verifique la clave o cambie de proveedor en la barra superior.",
            ))

    # -- reescritura determinista del texto -------------------------------
    corrected, typo_findings = apply_typo_rules(corrected)
    findings.extend(typo_findings)

    # -- verificaciones sobre el texto corregido --------------------------
    checks = [
        check_cement_thickness(corrected),
        check_tally_progress(corrected),
        check_rig_move(corrected),
        check_units(corrected),
        check_pressure_tests(corrected),
        check_dates(corrected),
        check_sacks(corrected),
        check_vague(corrected),
        check_well_profile(corrected, well_name),
    ]
    for group in checks:
        findings.extend(group)

    # -- aplicar correcciones demostrables al texto -----------------------
    for f in findings:
        fix = f.get("autofix")
        if fix and fix.get("old") and fix["old"] in corrected:
            corrected = corrected.replace(fix["old"], fix["new"], 1)
            f["applied"] = True

    # -- completitud + continuidad del pozo ------------------------------
    prior_state = get_well_state(well_name) if use_well_state else None
    period_fixed = parse_period(corrected, period_start, period_end)
    base = period_fixed if period_fixed.events else period
    events_for_completeness = [{
        "id": e.idx, "from": e.start, "to": e.end, "text": e.text, "line": e.line_start + 1,
    } for e in base.events]

    meta_ctx = dict(period.meta)
    meta_ctx.setdefault("pozo", well_name)
    comp = evaluate_completeness(events_for_completeness, corrected, meta_ctx, well_state=prior_state)
    corrected = append_completion_markers(corrected, comp["markers"])

    updated_state = prior_state
    if use_well_state:
        if prior_state:
            ctx_parts = []
            if prior_state.get("tubular"):
                ctx_parts.append(f"tubular: {prior_state['tubular']}")
            if prior_state.get("total_joints"):
                ctx_parts.append(f"total sarta: {prior_state['total_joints']} jtas")
            if prior_state.get("last_depth_ft") is not None:
                ctx_parts.append(f"última cota: {prior_state['last_depth_ft']:g} ft")
            if prior_state.get("fluid"):
                ctx_parts.append(f"fluido: {prior_state['fluid']}")
            if ctx_parts:
                findings.append(_finding(
                    "well", "info", f"🔵 CONTINUIDAD DEL POZO ({well_name})",
                    "Se heredó contexto previo del pozo: " + " · ".join(ctx_parts) + ".",
                    standard="Continuidad operativa entre lapsos",
                ))
        extracted_state = extract_well_state_from_text(corrected)
        if extracted_state:
            updated_state = upsert_well_state(well_name, extracted_state)

    # Hallazgo resumen de completitud
    if comp["missing_required"]:
        grouped: Dict[str, List[str]] = {}
        for m in comp["missing_required"]:
            grouped.setdefault(m["label"], []).append(f"{m['from']}–{m['to']}")
        parts = [f"{label} ({', '.join(ranges)})" for label, ranges in list(grouped.items())[:6]]
        detail = "; ".join(parts)
        findings.append(_finding(
            "completeness", "warning", f"🟠 COMPLETITUD {comp['score']}% — FALTAN DATOS",
            f"Campos obligatorios faltantes: {detail}"
            + (" …" if len(grouped) > 6 else ""),
            suggestion="Complete los campos marcados en la Caja 2 con '[completar: ...]'.",
        ))
        for m in comp["missing_required"][:4]:
            tips.append(f"Falta {m['label']} en {m['from']}-{m['to']} — ejemplo: {m['hint']}")
    else:
        findings.append(_finding(
            "completeness", "success", f"🟢 COMPLETITUD {comp['score']}%",
            f"Todas las operaciones detectadas ({', '.join(comp['ops_detected']) or 'ninguna'}) tienen sus campos obligatorios.",
        ))

    if comp["header"]["missing"]:
        req = [h["label"] for h in comp["header"]["missing"] if h["priority"] == "requerido"]
        if req:
            findings.append(_finding(
                "completeness", "info", "🔵 ENCABEZADO DEL REPORTE INCOMPLETO",
                "Faltan en el encabezado: " + ", ".join(req) + ".",
                suggestion="Agregue pozo y fecha al inicio del reporte.",
            ))

    # -- diff y orden -----------------------------------------------------
    diff_html = generate_diff_html(raw_text, corrected)
    findings.sort(key=lambda f: SEV_ORDER.get(f["severity"], 9))

    counters = {k: sum(1 for f in findings if f["severity"] == k) for k in SEV_ORDER}
    preflight = {
        "events": len(period.events),
        "coverage_pct": period.coverage_pct,
        "gaps_hours": round(sum(g["hours"] for g in period.gaps()), 2),
        "overlaps_hours": round(sum(o["hours"] for o in period.overlaps()), 2),
        "critical": counters["critical"],
        "warning": counters["warning"],
        "missing_required": len(comp["missing_required"]),
        "completeness": comp["score"],
    }

    if not tips:
        tips = [
            "Cada evento debe tener rango HH:MM-HH:MM, maniobra, herramienta y parámetro medible.",
            "Presiones de prueba: baja 250-350 psi y alta al rating; siempre con tiempo estabilizado.",
            "Cotas siempre con desde/hasta en ft MD y profundidad final del pozo.",
        ]

    return {
        "period": period.as_dict(),
        "visual_diff_html": diff_html,
        "corrected_spanish": corrected,
        "agent_findings": findings,
        "learning_tips": tips[:6],
        "completeness": {
            "score": comp["score"],
            "operation_score": comp["operation_score"],
            "header_score": comp["header_score"],
            "level": comp["level"],
            "ops_detected": comp["ops_detected"],
            "by_operation": comp["by_operation"],
            "header": comp["header"],
            "missing_required": comp["missing_required"],
        },
        "ai_status": ai_status,
        "preflight": preflight,
        "well_state": updated_state,
    }
