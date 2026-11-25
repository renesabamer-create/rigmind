import os
import json
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from src.engine.auditor import run_audit
from src.engine.translator import translate_to_iadc_english
from src.engine.llm_network import test_ai_provider_connection, detect_provider
from src.engine.learning_memory import load_memory, save_to_memory
from src.engine import store
from src.engine.export import build_docx, build_xlsx

app = FastAPI(title="RigMind - Asistente de reportes de pozo")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")), name="static")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _key_paths():
    """Ruta principal fuera de OneDrive; ruta legada para no perder la clave existente."""
    local = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".rigmind")
    return [
        os.path.join(local, "RigMind", "api_key"),
        os.path.join(BASE_DIR, "data", ".api_key"),
    ]


def server_api_key() -> Optional[str]:
    for env_k in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
        v = os.environ.get(env_k)
        if v and v.strip():
            return v.strip()
    for path in _key_paths():
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
            except Exception:
                continue
            if not content:
                continue
            if ":" in content:
                _, content = content.split(":", 1)
            return content.strip() or None
    return None


def _persist_api_key(key: str, provider: str) -> Optional[str]:
    try:
        path = _key_paths()[0]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{provider}:{key}")
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return path
    except Exception as e:
        return f"ERROR: {e}"


def _apply_api_key(key: str, provider: str) -> str:
    prov = detect_provider(key, requested=provider)
    env = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }.get(prov, "GEMINI_API_KEY")
    for k in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
        os.environ.pop(k, None)
    os.environ[env] = key
    return prov


if server_api_key():
    _apply_api_key(server_api_key(), "auto")


class ApiKeyConfigRequest(BaseModel):
    api_key: str
    provider: Optional[str] = "auto"

class TestApiKeyRequest(BaseModel):
    api_key: str
    provider: Optional[str] = "auto"

class AuditRequest(BaseModel):
    raw_text: str
    well_name: Optional[str] = "Yopo-1"
    period_start: Optional[str] = "00:00"
    period_end: Optional[str] = "24:00"
    api_key: Optional[str] = None
    provider: Optional[str] = "auto"
    use_ai: Optional[bool] = True

class TranslateRequest(BaseModel):
    polished_spanish: str
    well_name: Optional[str] = "Yopo-1"
    api_key: Optional[str] = None
    provider: Optional[str] = "auto"

class SaveMemoryRequest(BaseModel):
    category: str
    operation: str
    spanish_exemplar: str
    english_iadc: str
    learning_tip: str

class ReportPayload(BaseModel):
    well: Optional[str] = "Well"
    report_date: Optional[str] = None
    period_start: Optional[str] = "00:00"
    period_end: Optional[str] = "24:00"
    spanish: str = ""
    english: Optional[str] = ""
    findings: Optional[list] = []
    completeness: Optional[int] = 0
    operations: Optional[list] = []

@app.get("/api/config/api-key-status")
async def get_api_key_status():
    return {"has_key": bool(server_api_key())}

@app.post("/api/config/test-api-key")
async def api_test_key(req: TestApiKeyRequest):
    key = req.api_key.strip()
    if not key:
        return JSONResponse({"success": False, "error": "La clave no puede estar vacía."}, status_code=400)
    return test_ai_provider_connection(key, provider=req.provider or "auto")

@app.post("/api/config/api-key")
async def save_api_key(req: ApiKeyConfigRequest):
    key = req.api_key.strip()
    if not key:
        return JSONResponse({"error": "La clave no puede estar vacía."}, status_code=400)
    prov = _apply_api_key(key, req.provider or "auto")
    res = _persist_api_key(key, prov)
    if isinstance(res, str) and res.startswith("ERROR"):
        return JSONResponse({"error": f"No se pudo guardar la clave: {res[7:]}"}, status_code=500)
    return {"status": "ok", "has_key": True, "provider": prov, "stored_in": res}

@app.delete("/api/config/api-key")
async def delete_api_key():
    for k in ["GEMINI_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"]:
        os.environ.pop(k, None)
    for path in _key_paths():
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
    return {"status": "ok", "has_key": False}

@app.post("/api/audit")
async def api_audit(req: AuditRequest):
    """
    Etapa 1: audita el reporte de un lapso, lo sanea y devuelve la completitud
    por operación con hallazgos verificables (evidencia + norma + sugerencia).
    """
    raw_text = req.raw_text.strip()
    if not raw_text:
        return JSONResponse({"error": "El texto de entrada está vacío."}, status_code=400)
    if len(raw_text) > 60000:
        return JSONResponse({"error": "El reporte supera 60.000 caracteres. Divídalo por día o por turno."}, status_code=413)

    effective_key = (req.api_key or "").strip() or server_api_key()
    return run_audit(
        raw_text,
        period_start=req.period_start or "00:00",
        period_end=req.period_end or "24:00",
        api_key=effective_key,
        provider=req.provider or "auto",
        well_name=req.well_name or "Yopo-1",
        use_ai=True if req.use_ai is None else bool(req.use_ai),
        use_well_state=True,
    )

@app.post("/api/translate")
async def api_translate(req: TranslateRequest):
    """
    Etapa 2: traduce el texto en español YA revisado y completado por el usuario
    al inglés técnico IADC, y devuelve la verificación objetiva de la traducción.
    """
    text = req.polished_spanish.strip()
    if not text:
        return JSONResponse({"error": "El reporte saneado para traducir está vacío."}, status_code=400)

    effective_key = (req.api_key or "").strip() or server_api_key()
    english_translation, engine_source, trans_qaqc = translate_to_iadc_english(
        text, api_key=effective_key, provider=req.provider or "auto", well_name=req.well_name or "Yopo-1"
    )
    return {
        "english_iadc": english_translation,
        "engine_source": engine_source,
        "translation_qaqc": trans_qaqc,
    }

@app.post("/api/memory/save")
async def api_save_memory(req: SaveMemoryRequest):
    success = save_to_memory(req.dict())
    return {"success": success}

def _export_response(blob: bytes, fmt: str, well: str, report_date: str) -> Response:
    safe_well = "".join(c for c in (well or "Well") if c.isalnum() or c in "-_") or "Well"
    safe_date = (report_date or "").replace("/", "-") or "report"
    filename = f"DOR_{safe_well}_{safe_date}.{fmt}"
    media = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }[fmt]
    return Response(content=blob, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/reports")
async def api_reports():
    return {"reports": store.list_reports()}


@app.get("/api/report/{report_id}")
async def api_report_get(report_id: int):
    rep = store.get_report(report_id)
    if not rep:
        return JSONResponse({"error": "Reporte no encontrado."}, status_code=404)
    return rep


@app.post("/api/report/save")
async def api_report_save(req: ReportPayload):
    if not req.spanish.strip():
        return JSONResponse({"error": "No hay reporte en español para guardar."}, status_code=400)
    new_id = store.save_report(req.model_dump())
    return {"ok": True, "id": new_id}


@app.put("/api/report/{report_id}")
async def api_report_update(report_id: int, req: ReportPayload):
    ok = store.update_report(report_id, req.model_dump())
    return {"ok": ok}


@app.delete("/api/report/{report_id}")
async def api_report_delete(report_id: int):
    return {"ok": store.delete_report(report_id)}


@app.post("/api/report/export/{fmt}")
async def api_export_current(fmt: str, req: ReportPayload):
    if fmt not in ("docx", "xlsx"):
        return JSONResponse({"error": "Formato no soportado (use docx o xlsx)."}, status_code=400)
    data = req.model_dump()
    try:
        blob = build_docx(data) if fmt == "docx" else build_xlsx(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return _export_response(blob, fmt, data.get("well") or "Well", data.get("report_date") or "")


@app.get("/api/report/{report_id}/export/{fmt}")
async def api_export_saved(report_id: int, fmt: str):
    if fmt not in ("docx", "xlsx"):
        return JSONResponse({"error": "Formato no soportado (use docx o xlsx)."}, status_code=400)
    rep = store.get_report(report_id)
    if not rep:
        return JSONResponse({"error": "Reporte no encontrado."}, status_code=404)
    data = {
        "well": rep["well"], "report_date": rep["report_date"],
        "period_start": rep["period_start"], "period_end": rep["period_end"],
        "spanish": rep["spanish"], "english": rep["english"],
        "findings": rep["findings"], "completeness": rep["completeness"],
    }
    try:
        blob = build_docx(data) if fmt == "docx" else build_xlsx(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return _export_response(blob, fmt, rep["well"], rep["report_date"] or "")


@app.get("/api/memory")
async def api_get_memory():
    return load_memory()

@app.get("/api/sample")
async def api_sample():
    sample_text = """POZO: Yopo-1
FECHA: 24-Nov-2026
EQUIPO: ERR TSW-01
OPERADORA: Sabana Resources / CONTRATISTA: TSW
FLUIDO: 9.2 ppg KCl
DÍA: 4 de 8

07:00 - 08:00: Realizó reunión de seguridad y preoperacional con todo el personal, revisó procedimiento para retomar operaciones. SWU: 42.5 klb y SWD: 37.7 klb, ok.
08:00 - 09:30: Continuó RIH BHA No. 1 BPHM CSG 7" con TBG 3 1/2" EU 9.3 lb/ft en sencillos desde 5473 ft hasta 5720 ft, SWU 45 klb, SWD: 39.5 klb, vel: 10 jtas/h = 313 ft/h.
09:30 - 11:00: Sentó Bridge Plug hidromecánico de 7" @ 5720 ft: bombeó a 1.5 bpm con bola de 1.25", presurizó hasta 3200 psi observando caída súbita a 0 psi. Verificó anclaje con 40 klb de sobretensión (86 klb total) x 5 min. Bajó sarta y aplicó 7 klb sobre el HMBP. Aplicó tensión nuevamente hasta 86 klb x 10 min.
11:00 - 12:00: Liberó del HMBP con 10 vueltas a la derecha bajo 48 klb de tensión. Bombeó 10 bbl agua industrial pozo lleno y probó integridad del HMBP 7" con 500 psi x 15 min con bomba de cementación, ok.
12:00 - 13:00: Personal tomando alimentos (almuerzo).
13:00 - 16:00: Circuló píldora de limpieza: 5 bbl surfactante @ 1.5 bpm + 5 bbl goma xántica @ 1.5 bpm. Desplazó con 220 bbl agua @ 3 bpm con 200 psi.
16:00 - 16:30: Charla preoperacional para balanceo de tapón de cemento de fondo.
16:30 - 18:00: NPT Clima: Suspendió operaciones por tormenta eléctrica N-III.
18:00 - 18:30: Retomó charla de seguridad antes de cementar.
18:30 - 20:00: Mezcló cemento y realizó tapón de fondo de 5720 ft a 5331 ft, 146 ft de espesor así: 5 bbl preflujo agua fresca, 16 bbl lechada cemento 15.8 ppg Clase G Holcim ____ a 3 bpm con 80 psi. Desplazó con 36 bbl de agua. Evidenció succión en backflow. Recogió 3 testigos.
20:00 - 22:00: POOH BHA No. 1 con tubería combinada quebrando 25 jtas a racks desde 5720 ft hasta 4944 ft. SWU 40 klb sin arrastre.
22:00 - 22:30: Conectó cabeza y reversó 60 bbl hasta retorno limpio. POOH hasta 4788 ft. Inició tiempo de WOC.
22:30 - 24:00: WOC (1.5/10 h), avance 15%."""
    return {"sample_text": sample_text}

@app.get("/", response_class=HTMLResponse)
async def index():
    html_content = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RigMind | Asistente de reportes de pozo</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg?v=7">
    <link rel="shortcut icon" href="/static/favicon.svg?v=7">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Space+Grotesk:wght@500;600;700&family=Hanken+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/app.css?v=7">
</head>
<body>

    <!-- TOP TELEMETRY BAR -->
    <header>
        <div class="logo-area">
            <img src="/static/favicon.svg?v=7" alt="RigMind" class="brand-logo">
            <div>
                <div class="logo-title"><span class="brand-rig">Rig</span><span class="brand-mind">Mind</span> <span style="font-size:0.75rem; color:var(--text-muted); font-weight:400">· Asistente de reportes</span></div>
                <div style="font-size:0.7rem; color:var(--text-muted)">Audita un lapso, completa el reporte, traduce a inglés de operaciones</div>
            </div>
            <span class="badge badge-amber" id="rigStatusBadge">Reglas locales</span>
        </div>

        <div class="meta-controls">
            <label style="font-size:0.75rem; color:var(--text-muted)">Pozo:</label>
            <input type="text" id="wellNameInput" class="meta-input" value="Yopo-1" style="width:90px">

            <label style="font-size:0.75rem; color:var(--text-muted)">Lapso:</label>
            <input type="text" id="periodStartInput" class="meta-input" value="00:00" style="width:60px" title="Hora de inicio del lapso que cubre el reporte (HH:MM)">
            <span style="color:var(--text-muted)">→</span>
            <input type="text" id="periodEndInput" class="meta-input" value="24:00" style="width:60px" title="Hora final del lapso que cubre el reporte (HH:MM o 24:00)">
            <span class="badge badge-amber" id="timeBalanceBadge">Lapso sin analizar</span>

            <label style="font-size:0.75rem; color:var(--text-muted)">Historial:</label>
            <select id="historySelect" class="meta-input" style="max-width:250px" onchange="loadSelectedReport()">
                <option value="">— reportes guardados —</option>
            </select>

            <button class="btn btn-ghost" onclick="loadSampleData()">📂 Cargar Ejemplo Yopo-1</button>
            <!-- CLAVE DE IA: se guarda en el equipo, no en el navegador -->
            <div id="apiVaultContainer">
                <div style="display:inline-flex; align-items:center; gap:6px; background:#0E131A; border:1px solid var(--border); padding:3px 8px; border-radius:4px;" title="Seleccione proveedor y pegue su API Key (OpenAI, DeepSeek, Claude, Groq o Gemini).">
                    <select id="providerSelect" class="meta-input" style="padding:2px 4px; font-size:0.75rem; background:#080B0F; border:1px solid #232E3E; color:var(--text-main); border-radius:3px;">
                        <option value="auto">🤖 Auto-Detectar</option>
                        <option value="deepseek">🐳 DeepSeek (V3 / R1)</option>
                        <option value="openai">🟢 OpenAI (GPT-4o)</option>
                        <option value="anthropic">🟣 Claude 3.5</option>
                        <option value="groq">⚡ Groq (Llama 3.3)</option>
                        <option value="gemini">🔵 Google Gemini</option>
                    </select>
                    <input 
                        type="password" 
                        id="secureApiKeyInput" 
                        class="api-input" 
                        placeholder="Pegar API Key..." 
                        autocomplete="off" 
                        spellcheck="false"
                        onkeydown="if(event.key==='Enter') saveApiKeyClient()"
                        style="width:140px; letter-spacing:1px;"
                    >
                    <button type="button" class="btn-vault-save" onclick="saveApiKeyClient()" title="Guardar Clave de IA">💾</button>
                </div>
            </div>
        </div>
    </header>

    <!-- COMPLETITUD DEL REPORTE -->
    <div class="maturity-bar-wrapper">
        <div class="maturity-title">📊 Completitud del reporte: <span id="tierLabel" style="color:var(--text-muted)">Sin analizar</span></div>
        <div class="progress-container">
            <div class="progress-bar" id="maturityProgressBar"></div>
        </div>
        <div id="missingTipsText" style="font-size:0.75rem; color:var(--text-muted)">
            Pegue el reporte del lapso y presione "⚡ 1. Auditar" para ver qué falta y qué está mal.
        </div>
    </div>


    <!-- 4-BOX MAIN WORKSPACE -->
    <nav class="mobile-quick-nav" aria-label="Navegación rápida móvil">
        <a href="#box1Card">1. Crudo</a>
        <a href="#box2Card">2. Revisar</a>
        <a href="#box3Card">3. Hallazgos</a>
        <a href="#box4Card">4. Inglés</a>
    </nav>
    <div class="grid-4box">

        <!-- CAJA 1: ENTRADA CRUDA (ESPAÑOL) -->
        <div class="card" id="box1Card">
            <div class="card-header">
                <div class="card-title"><span>📝</span> CAJA 1: Entrada Cruda (Español)</div>
                <button class="btn" id="btnAuditStage1" onclick="runStage1Audit()">⚡ 1. Auditar Reporte</button>
            </div>
            <div class="card-body">
                <textarea id="rawTextInput" class="editor-box" placeholder="Pegue aquí el reporte o notas de campo en español..."></textarea>
                <div class="status-strip">
                    <span>Duración calculada: <b id="calcDurText">0.0 h</b></span>
                    <span id="gapNoticeText" style="color:var(--amber)"></span>
                </div>
            </div>
        </div>

        <!-- CAJA 2: REPORTE SANEADO & EDITOR INTERACTIVO (ESPAÑOL) -->
        <div class="card" id="box2Card">
            <div class="card-header">
                <div class="card-title"><span>✏️</span> CAJA 2: Reporte Saneado & Auditoría (Español)</div>
                <div style="display:flex; gap:6px; flex-wrap:wrap;">
                    <button class="btn btn-ghost" id="btnNextPlaceholder" onclick="focusNextPlaceholder()" style="color:var(--amber); border-color:rgba(245, 158, 11, 0.4);" title="Saltar y seleccionar el siguiente campo pendiente [___] (o presione Tab dentro del editor)">🎯 Llenar [___]</button>
                    <button class="btn btn-ghost" id="btnReauditBox2" onclick="reauditBox2()" title="Re-evaluar el texto ya editado en la Caja 2 (sin usar IA, instantáneo)">🔄 Re-auditar</button>
                    <button class="btn btn-ghost" id="btnToggleDiff" onclick="toggleDiffMode()" title="Alternar entre modo editor interactivo y vista comparativa diff">🔍 Ver Diff</button>
                    <button class="btn btn-emerald" id="btnTranslateStage2" onclick="runStage2Translate()" style="font-weight:700;" title="Traducir a inglés de operaciones usando la IA seleccionada">🚀 2. Traducir a Inglés IADC</button>
                </div>
            </div>
            <div class="card-body">
                <textarea id="polishedTextInput" class="editor-box" placeholder="Aquí aparecerá el reporte saneado tras presionar '⚡ 1. Auditar Reporte'. Complete aquí los campos que el auditor marcó como [completar: ...] y luego traduzca."></textarea>
                <div id="diffViewBox" class="diff-view-box" style="display:none;">Vista comparativa: rojo = lo que se corrigió, verde = la corrección, ámbar = campos por completar.</div>
                
                <!-- BARRA DE ESTADO DEL LAPSO Y DEL REPORTE -->
                <div class="preflight-strip" id="preflightStrip">
                    <span style="font-weight:700; color:var(--text-muted); text-transform:uppercase;">Estado:</span>
                    <span class="pf-chip" id="pfHoursChip">⏱️ Lapso: sin analizar</span>
                    <span class="pf-chip" id="pfMathChip">📐 Aritmética: sin analizar</span>
                    <span class="pf-chip" id="pfNormsChip">📏 Completitud: sin analizar</span>
                    <span class="pf-chip" id="pfBlanksChip">✍️ Campos faltantes: —</span>
                </div>

                <ul class="tips-list" id="tipsListContainer"></ul>
            </div>
        </div>

        <!-- CAJA 3: AUDITORÍA TÉCNICA -->
        <div class="card" id="box3Card">
            <div class="card-header">
                <div class="card-title"><span>🔎</span> CAJA 3: Hallazgos y qué falta completar</div>
                <span class="badge badge-cyan" id="findingsCountBadge">Sin analizar</span>
            </div>
            <div class="card-body">
                <div class="findings-list" id="findingsListContainer">
                    <div style="font-size:0.8rem; color:var(--text-muted); padding:10px;">
                        Al auditar verá aquí, en orden de gravedad:
                        <br>• <b>Errores demostrables</b> (restas de tapón, avance de juntas, cargas, presiones fuera de norma) con la línea y la cita.
                        <br>• <b>Qué falta completar</b> por operación: POOH/RIH, HMBP, tapón de cemento, prueba de BOP, circulación, wireline, rig move, ESP, NPT.
                        <br>• <b>Sugerencias de redacción</b> para frases sin contenido técnico.
                        <br>Todo hallazgo indica la norma o práctica aplicable y cómo corregirlo en la Caja 2.
                    </div>
                </div>
            </div>
        </div>

        <!-- CAJA 4: TRADUCCIÓN EN INGLÉS -->
        <div class="card" id="box4Card">
            <div class="card-header">
                <div class="card-title"><span>🇬🇧</span> CAJA 4: Traducción a inglés de operaciones</div>
                <div style="display:flex; gap:6px; flex-wrap:wrap;">
                    <button class="btn btn-ghost" id="btnToggleAligned" onclick="toggleAlignedView()" title="Ver tabla comparativa hora a hora (Español ↔ Inglés)">🔀 Vista alineada</button>
                    <button class="btn btn-ghost" onclick="saveReport()" title="Guardar el reporte en el historial local">💾 Guardar</button>
                    <button class="btn btn-ghost" onclick="exportReport('docx')" title="Descargar Word con hallazgos y textos">⬇ Word</button>
                    <button class="btn btn-ghost" onclick="exportReport('xlsx')" title="Descargar Excel con resumen, operaciones y hallazgos">⬇ Excel</button>
                    <button class="btn btn-ghost" onclick="copyEnglishTranslation()" title="Copiar texto en inglés">📋 Copiar</button>
                    <button class="btn btn-ghost" onclick="copyBilingualDOR()" title="Copiar reporte bilingüe (español revisado + inglés)">📑 Copiar DOR Bilingüe</button>
                    <button class="btn btn-emerald" onclick="saveToGoldenMemory()" title="Guardar ejemplo en memoria local">⭐ Guardar ejemplo</button>
                </div>
            </div>
            <div class="card-body">
                <div id="englishOutputBox" class="english-box">Aquí aparecerá el texto en inglés después del Paso 2...</div>
                <div id="alignedViewBox" class="aligned-view-box" style="display:none;"></div>
                <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.75rem; color:var(--text-muted); margin-top:6px; flex-wrap:wrap; gap:8px;">
                    <div>
                        <span>⚡ Motor: <b id="translationEngineBadge" style="color:var(--amber)">En espera del Paso 2</b></span>
                        <span id="translationAuditBadge" class="badge badge-cyan" style="display:none; margin-left:8px;">Verificación</span>
                        <span id="dataParityBadge" class="badge badge-cyan" style="display:none; margin-left:6px;">Datos</span>
                    </div>
                    <span id="copyConfirmNotice" style="color:var(--emerald)"></span>
                </div>
            </div>
        </div>


    </div>

    <script src="/static/app.js?v=7"></script>
</body>
</html>"""
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
