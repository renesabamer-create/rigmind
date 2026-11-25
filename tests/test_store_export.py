"""Pruebas de historial SQLite y exportación a .docx / .xlsx."""

import os
import tempfile

from src.engine import store
from src.engine.export import build_docx, build_xlsx

PAYLOAD = {
    "well": "Yopo-1",
    "report_date": "2026-11-24",
    "period_start": "07:00",
    "period_end": "24:00",
    "spanish": "07:00 - 08:00: Reunión de seguridad.\n08:00 - 09:30: RIH hasta 5720 ft.",
    "english": "07:00 - 08:00: Safety meeting.\n08:00 - 09:30: RIH to 5720 ft.",
    "findings": [{
        "severity": "critical", "badge": "🔴 ERROR", "agent": "cementing",
        "message": "5720 - 5331 = 389 ft", "evidence": {"line": 3, "quote": "146 ft de espesor"},
        "standard": "NORSOK D-010", "suggestion": "Escriba 389 ft",
    }],
    "completeness": 78,
    "operations": [{"from": "08:00", "to": "09:30", "label": "RIH", "score": 80,
                    "missing": [{"label": "tally"}]}],
}


def _temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store.DB_PATH = path
    return path


def test_store_roundtrip():
    path = _temp_db()
    try:
        rid = store.save_report(PAYLOAD)
        assert rid > 0
        rows = store.list_reports()
        assert rows[0]["id"] == rid
        assert rows[0]["well"] == "Yopo-1"
        assert rows[0]["completeness"] == 78
        assert rows[0]["has_english"] is True

        rep = store.get_report(rid)
        assert rep["spanish"].startswith("07:00")
        assert len(rep["findings"]) == 1
        assert rep["findings"][0]["evidence"]["line"] == 3

        assert store.update_report(rid, {**PAYLOAD, "english": "updated", "completeness": 90})
        assert store.get_report(rid)["english"] == "updated"
        assert store.get_report(rid)["completeness"] == 90

        assert store.delete_report(rid)
        assert store.get_report(rid) is None
    finally:
        os.remove(path)


def test_docx_is_valid_zip():
    blob = build_docx(PAYLOAD)
    assert blob[:2] == b"PK"
    assert len(blob) > 5000


def test_xlsx_is_valid_zip():
    blob = build_xlsx(PAYLOAD)
    assert blob[:2] == b"PK"
    assert len(blob) > 5000


def test_export_without_findings():
    data = dict(PAYLOAD, findings=[], english="", operations=[])
    assert build_docx(data)[:2] == b"PK"
    assert build_xlsx(data)[:2] == b"PK"


def test_well_state_continuity_across_audits():
    from src.engine.auditor import run_audit
    path = _temp_db()
    try:
        r1 = run_audit(
            "POZO: Test-Continuidad\nFECHA: 24-Nov-2026\nFLUIDO: 9.2 ppg KCl\n"
            '07:00 - 09:00: POOH TBG 3-1/2" EU 9.3 lb/ft quebrando en sencillos desde 5720 ft hasta 4944 ft (25/180 jtas), avance: 13.9%, SWU 45 klb, SWD 39 klb.',
            period_start="07:00", period_end="09:00", well_name="Test-Continuidad",
            use_ai=False, use_well_state=True,
        )
        assert r1["well_state"]["total_joints"] == 180
        assert "3-1/2" in (r1["well_state"]["tubular"] or "")

        r2 = run_audit(
            "POZO: Test-Continuidad\nFECHA: 24-Nov-2026\n"
            "09:00 - 11:00: POOH quebrando en sencillos desde 4944 ft hasta 4100 ft (52/180 jtas), avance: 28.9%, SWU 41 klb, SWD 36 klb.",
            period_start="09:00", period_end="11:00", well_name="Test-Continuidad",
            use_ai=False, use_well_state=True,
        )
        assert any("CONTINUIDAD DEL POZO" in f["badge"] for f in r2["agent_findings"])
        missing_keys = {m["key"] for m in r2["completeness"]["missing_required"]}
        assert "tubular" not in missing_keys
    finally:
        os.remove(path)
