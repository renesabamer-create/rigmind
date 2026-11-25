"""Pruebas del motor: cronología, aritmética, completitud, diff y traducción.

Ejecutar:  python -m pytest -q
"""

import re

from src.engine.auditor import run_audit
from src.engine.completeness import evaluate, detect_ops
from src.engine.period import parse_period
from src.engine.translator import audit_translation_qaqc

SAMPLE = """POZO: Yopo-1
FECHA: 24-Nov-2026
EQUIPO: ERR TSW-01

07:00 - 08:00: Reunión de seguridad con todo el personal.
08:00 - 09:30: Continuó RIH BHA No. 1 con TBG 3 1/2" 9.3 lb/ft N-80 EUE en sencillos desde 5473 ft hasta 5720 ft, SWU 45 klb, SWD 39.5 klb, vel 10 jtas/h.
09:30 - 11:00: Sentó Bridge Plug hidromecánico de 7" @ 5720 ft. Presurizó hasta 3200 psi con caída a 0 psi. Verificó anclaje con 40 klb x 5 min.
11:00 - 12:00: Liberó del HMBP con 10 vueltas a la derecha bajo 48 klb. Probó integridad con 500 psi x 15 min.
12:00 - 13:00: Personal tomando alimentos.
13:00 - 16:00: Circuló píldora de limpieza: 5 bbl surfactante @ 1.5 bpm. Desplazó con 220 bbl agua @ 3 bpm con 200 psi.
16:00 - 18:30: NPT Clima: Suspendió operaciones por tormenta eléctrica N-III.
18:30 - 20:00: Mezcló cemento y realizó tapón de fondo de 5720 ft a 5331 ft, 146 ft de espesor. 16 bbl de lechada 15.8 ppg Clase G a 3 bpm con 80 psi. Desplazó con 36 bbl. WOC 10 h. Recogió 3 testigos.
"""


# --------------------------------------------------------------------------
# Cronología de un lapso (no 24 h forzadas)
# --------------------------------------------------------------------------
def test_period_full_coverage_without_gaps():
    rep = parse_period(SAMPLE, "07:00", "20:00")
    assert rep.coverage_pct == 100.0
    assert rep.gaps() == []
    assert rep.documented_hours == 13.0
    assert len(rep.events) == 8


def test_period_detects_gap():
    txt = "07:00 - 08:00: A.\n10:00 - 11:00: B."
    rep = parse_period(txt, "07:00", "11:00")
    assert rep.coverage_pct < 60
    gaps = rep.gaps()
    assert len(gaps) == 1
    assert gaps[0]["from"] == "08:00" and gaps[0]["to"] == "10:00"
    assert gaps[0]["hours"] == 2.0


def test_period_detects_overlap():
    txt = "07:00 - 09:00: A.\n08:30 - 10:00: B."
    rep = parse_period(txt, "07:00", "10:00")
    overlaps = rep.overlaps()
    assert len(overlaps) == 1
    assert overlaps[0]["hours"] == 0.5
    assert rep.repeated_hours == 0.5


def test_period_sequential_mode_infers_end_times():
    txt = "06:00: Inició RIH.\n07:00: Siguió RIH.\n08:00: Terminó RIH."
    rep = parse_period(txt, "06:00", "08:00")
    assert [e.end for e in rep.events] == ["07:00", "08:00", "08:00"]
    assert rep.events[0].duration_h == 1.0
    assert rep.mode if hasattr(rep, "mode") else True


def test_period_starting_late_is_info_not_error():
    txt = "07:00 - 08:00: A."
    rep = parse_period(txt, "00:00", "24:00")
    codes = [i["code"] for i in rep.issues]
    assert "inicio_tardio" in codes
    assert all(i["severity"] != "critical" for i in rep.issues)


# --------------------------------------------------------------------------
# Aritmética demostrable
# --------------------------------------------------------------------------
def test_cement_thickness_error_is_corrected_in_text():
    r = run_audit(SAMPLE, "07:00", "24:00", use_ai=False)
    assert "389 ft de espesor" in r["corrected_spanish"]
    assert "146 ft de espesor" not in r["corrected_spanish"]
    crit = [f for f in r["agent_findings"] if f["severity"] == "critical"]
    assert any("ESPESOR" in f["badge"] for f in crit)
    assert any(f.get("applied") for f in crit)


def test_tally_progress_error():
    txt = "07:00 - 08:00: POOH 4/150 jtas, avance 5.0%."
    r = run_audit(txt, "07:00", "08:00", use_ai=False)
    assert "avance: 2.7%" in r["corrected_spanish"]
    assert any("AVANCE" in f["badge"] for f in r["agent_findings"])


def test_absurd_klb_units():
    txt = "07:00 - 08:00: Tensionó con 68000 klbs el peso de la sarta."
    r = run_audit(txt, "07:00", "08:00", use_ai=False)
    assert "68 klb (68,000 lb)" in r["corrected_spanish"]


def test_bop_low_pressure_out_of_range():
    txt = "07:00 - 08:00: Prueba de BOP anular en baja con 500 psi x 5 min."
    r = run_audit(txt, "07:00", "08:00", use_ai=False)
    assert any("BAJA FUERA DE RANGO" in f["badge"] for f in r["agent_findings"])


def test_invalid_date_is_flagged_but_not_invented():
    txt = "07:00 - 08:00: Reporte del 31/11/2026."
    r = run_audit(txt, "07:00", "08:00", use_ai=False)
    assert "31/11/2026" in r["corrected_spanish"]
    assert any("FECHA INEXISTENTE" in f["badge"] for f in r["agent_findings"])


# --------------------------------------------------------------------------
# Completitud por operación
# --------------------------------------------------------------------------
def test_operation_detection_priority():
    assert detect_ops("Sentó Bridge Plug hidromecánico de 7\" a 5720 ft")[0] == "HMBP"
    assert detect_ops("Charla preoperacional para balancear tapón de cemento")[0] == "SAFETY"
    assert detect_ops("Circuló píldora de limpieza con 5 bbl")[0] == "CIRCULATION"


def test_hmbp_spanning_two_events_is_grouped():
    comp = evaluate(
        [
            {"id": 1, "from": "09:30", "to": "11:00",
             "text": "Sentó HMBP 7\" @ 5720 ft. Presurizó a 3200 psi. Verificó anclaje con 40 klb x 5 min.", "line": 1},
            {"id": 2, "from": "11:00", "to": "12:00",
             "text": "Liberó del HMBP con 10 vueltas a la derecha bajo 48 klb. Probó integridad con 500 psi x 15 min.", "line": 2},
        ],
        "HMBP 7\" 5720 ft",
        {"pozo": "Yopo-1"},
    )
    hm = [o for o in comp["by_operation"] if o["op"] == "HMBP"]
    assert len(hm) == 1
    assert hm[0]["span_events"] == 2
    assert hm[0]["score"] >= 85


def test_markers_only_for_required_fields():
    r = run_audit(SAMPLE, "07:00", "24:00", use_ai=False)
    markers = re.findall(r"\[completar: ([^\]]+)\]", r["corrected_spanish"])
    assert markers, "debe haber al menos un campo obligatorio faltante"
    for m in markers:
        assert "carta Barton" not in m  # recomendado, no va al texto


def test_complete_report_scores_high():
    txt = (
        "POZO: Yopo-1\nFECHA: 24-Nov-2026\nEQUIPO: ERR TSW-01\nOPERADORA: Sabana / CONTRATISTA: TSW\n"
        "FLUIDO: 9.2 ppg KCl\nDÍA: 4 de 8\n\n"
        "06:00 - 07:00: Reunión de seguridad (PJSM) con todo el personal, checklist diario y JSA firmados.\n"
        "07:00 - 08:00: RIH sarta con TBG 3-1/2\" 9.3 lb/ft N-80 EUE en sencillos desde superficie hasta 5720 ft, 26/150 jtas, avance 17.3%, SWU 45 klb, SWD 39.5 klb, velocidad 10 jtas/h.\n"
        "08:00 - 10:00: Sentó HMBP 7\" @ 5720 ft. Presurizó a 3200 psi con caída a 0 psi. Verificó anclaje con 40 klb x 5 min. Aplicó 7 klb. Liberó con 10 vueltas a la derecha. Probó integridad con 500 psi x 15 min y registró carta Barton.\n"
        "10:00 - 12:00: Mezcló cemento y realizó tapón de fondo de 5720 ft a 5331 ft, 389 ft de espesor. 5 bbl de preflujo, 16 bbl de lechada Clase G a 15.8 ppg a 3 bpm con 80 psi. Desplazó con 36 bbl. WOC 10 h. Verificó TOC con 10 klb. Recogió 3 testigos.\n"
    )
    r = run_audit(txt, "06:00", "12:00", use_ai=False)
    assert r["completeness"]["score"] >= 80, r["completeness"]["by_operation"]
    assert not [f for f in r["agent_findings"] if f["severity"] == "critical"]


# --------------------------------------------------------------------------
# Seguridad y traducción
# --------------------------------------------------------------------------
def test_diff_escapes_user_html():
    r = run_audit('07:00 - 08:00: <img src=x onerror="alert(1)"> & <script>alert(2)</script>')
    html = r["visual_diff_html"]
    assert "<img src=x" not in html
    assert "<script>" not in html
    assert "&lt;img" in html


def test_translation_qaqc_flags_spanish_residue():
    q = audit_translation_qaqc("Verificó anclaje con 40 klb de sobretensión. Bajó sarta.", "texto")
    assert q["status"] == "REVISAR_ESPANOL"
    assert "verificó" in q["flagged_tokens"]


def test_translation_qaqc_passes_clean_english():
    es = "07:00 - 08:00: RIH tubería hasta 5720 ft con 45 klb."
    en = "07:00 - 08:00: RIH tubing to 5720 ft with 45 klb."
    q = audit_translation_qaqc(en, es)
    assert q["status"] == "VERIFICADO"
    assert q["data_parity_pct"] == 100.0


def test_translation_qaqc_detects_missing_numbers():
    es = "Bombeó 60 bbl a 3 bpm con 200 psi."
    en = "Pumped fluid at 3 bpm."
    q = audit_translation_qaqc(en, es)
    assert q["status"] == "REVISAR_DATOS"
    assert any("60 bbl" in x for x in q["missing_numbers"])


def test_new_operations_completeness_detected():
    from src.engine.completeness import detect_ops
    assert "FISHING" == detect_ops('Bajó overshot 5-3/4" en pesca @ 5410 ft')[0]
    assert "MILLING" == detect_ops('Molió tapón con molino plano 6-1/8" desde 5330 ft hasta 5385 ft')[0]
    assert "STIMULATION" == detect_ops("Realizó acidificación con 30 bbl HCl 15% a 2.5 bpm con 1850 psi")[0]
    assert "COILED_TUBING" == detect_ops('Bajó coiled tubing 1-3/4" hasta 6150 ft bombeando a 1.8 bpm con 2400 psi')[0]
    assert "SWABBING" == detect_ops("Realizó 8 corridas de swabbing hasta 4200 ft recuperando 28 bbl")[0]


def test_learning_memory_selects_relevant():
    from src.engine.learning_memory import select_relevant_examples
    exs = select_relevant_examples("Asentó bridge plug HMBP 7 pulgadas a 5720 ft con 3200 psi", limit=2)
    assert isinstance(exs, list)
    assert len(exs) >= 1
