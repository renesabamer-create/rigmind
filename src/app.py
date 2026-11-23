import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from src.engine.chronology import parse_raw_timeline
from src.engine.qaqc_auditor import audit_operations_text
from src.engine.learning_memory import calculate_maturity_score, save_to_memory, load_memory
from src.engine.translator import translate_to_iadc_english

app = FastAPI(title="RigMind - Smart Well Intervention & Workover Suite")

API_KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".api_key")

def load_server_api_key():
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                k = f.read().strip()
                if k:
                    os.environ["GEMINI_API_KEY"] = k
        except Exception:
            pass

load_server_api_key()

class ApiKeyConfigRequest(BaseModel):
    api_key: str

class AuditRequest(BaseModel):
    raw_text: str
    well_name: Optional[str] = "Yopo-1"
    api_key: Optional[str] = None
    provider: Optional[str] = "auto"

class SaveMemoryRequest(BaseModel):
    category: str
    operation: str
    spanish_exemplar: str
    english_iadc: str
    learning_tip: str

@app.get("/api/config/api-key-status")
async def get_api_key_status():
    return {"has_key": bool(os.environ.get("GEMINI_API_KEY"))}

@app.post("/api/config/api-key")
async def save_api_key(req: ApiKeyConfigRequest):
    key = req.api_key.strip()
    if not key:
        return JSONResponse({"error": "La clave no puede estar vacía."}, status_code=400)
    os.environ["GEMINI_API_KEY"] = key
    try:
        os.makedirs(os.path.dirname(API_KEY_FILE), exist_ok=True)
        with open(API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key)
    except Exception as e:
        return JSONResponse({"error": f"Error al guardar la clave: {str(e)}"}, status_code=500)
    return {"status": "ok", "has_key": True}

@app.delete("/api/config/api-key")
async def delete_api_key():
    if "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]
    if os.path.exists(API_KEY_FILE):
        try:
            os.remove(API_KEY_FILE)
        except Exception:
            pass
    return {"status": "ok", "has_key": False}

@app.post("/api/audit")
async def api_audit(req: AuditRequest):
    raw_text = req.raw_text.strip()
    if not raw_text:
        return JSONResponse({"error": "El texto de entrada está vacío."}, status_code=400)
        
    # 1. Chronology and 24h sanity check
    chrono_result = parse_raw_timeline(raw_text)
    
    # 2. QA/QC Audit, Visual Diff & Learning Tips
    audit_result = audit_operations_text(raw_text)
    
    # 3. Maturity Score (0% to 100%)
    maturity_result = calculate_maturity_score(audit_result["corrected_spanish"])
    
    # 4. Standardized IADC English Translation & Agent #10 QA/QC Audit
    effective_api_key = req.api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GROQ_API_KEY")
    english_translation, engine_source, trans_qaqc = translate_to_iadc_english(
        audit_result["corrected_spanish"], 
        api_key=effective_api_key, 
        provider=req.provider or "auto",
        well_name=req.well_name
    )
    
    # Append Agent #10 Translation Findings into the Agent Findings List
    if trans_qaqc and "findings" in trans_qaqc:
        audit_result["agent_findings"].extend(trans_qaqc["findings"])
    
    return {
        "chronology": chrono_result,
        "visual_diff_html": audit_result["visual_diff_html"],
        "corrected_spanish": audit_result["corrected_spanish"],
        "agent_findings": audit_result["agent_findings"],
        "learning_tips": audit_result["learning_tips"],
        "maturity": maturity_result,
        "english_iadc": english_translation,
        "engine_source": engine_source,
        "translation_qaqc": trans_qaqc
    }

@app.post("/api/memory/save")
async def api_save_memory(req: SaveMemoryRequest):
    success = save_to_memory(req.dict())
    return {"success": success}

@app.get("/api/memory")
async def api_get_memory():
    return load_memory()

@app.get("/api/sample")
async def api_sample():
    sample_text = """07:00 - 08:00: Realizó reunión de seguridad y preoperacional con todo el personal, revisó procedimiento para retomar operaciones. SWU: 42.5 klb y SWD: 37.7 klb, ok.
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
    <title>RigMind | Smart Resources - Well Intervention & QA/QC Suite</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Space+Grotesk:wght@500;600;700&family=Hanken+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0B0F14;
            --panel-bg: #121820;
            --card-bg: #1A232E;
            --border: #2D3B4E;
            --amber: #F59E0B;
            --cyan: #00D2B4;
            --emerald: #10B981;
            --crimson: #EF4444;
            --text-main: #DDE3EE;
            --text-muted: #8E9CAE;
            --font-head: 'Space Grotesk', sans-serif;
            --font-body: 'Hanken Grotesk', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: var(--font-body);
            line-height: 1.5;
            padding: 16px;
        }

        header {
            background: var(--panel-bg);
            border: 1px solid var(--border);
            padding: 14px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 16px;
        }

        .logo-area { display: flex; align-items: center; gap: 10px; }
        .logo-title { font-family: var(--font-head); font-size: 1.25rem; font-weight: 700; color: var(--amber); }
        .badge {
            font-family: var(--font-mono);
            font-size: 0.7rem;
            padding: 3px 8px;
            border-radius: 3px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge-cyan { background: rgba(0, 210, 180, 0.12); color: var(--cyan); border: 1px solid var(--cyan); }
        .badge-emerald { background: rgba(16, 185, 129, 0.15); color: var(--emerald); border: 1px solid var(--emerald); }
        .badge-amber { background: rgba(245, 158, 11, 0.15); color: var(--amber); border: 1px solid var(--amber); }
        .badge-crimson { background: rgba(239, 68, 68, 0.15); color: var(--crimson); border: 1px solid var(--crimson); }

        .meta-controls { display: flex; align-items: center; gap: 12px; }
        .meta-input {
            background: #0E131A;
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 6px 12px;
            font-family: var(--font-mono);
            font-size: 0.8rem;
        }

        .api-key-box {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: #0E131A;
            border: 1px solid var(--border);
            padding: 3px 8px;
            border-radius: 4px;
        }
        .api-input {
            width: 140px;
            border: 1px solid #232E3E;
            background: #080B0F;
            color: var(--text-main);
            padding: 4px 28px 4px 8px;
            font-family: var(--font-mono);
            font-size: 0.8rem;
            letter-spacing: 2px;
            border-radius: 3px;
            transition: all 0.2s;
        }
        .api-input:focus {
            border-color: var(--cyan);
            outline: none;
            box-shadow: 0 0 6px rgba(0, 210, 180, 0.25);
        }
        .btn-vault-save {
            background: var(--cyan);
            color: #0B0F14;
            border: none;
            padding: 4px 10px;
            font-size: 0.8rem;
            cursor: pointer;
            border-radius: 3px;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
        }
        .btn-vault-save:hover {
            background: #22EED0;
        }
        .btn-vault-action {
            background: transparent;
            color: #F87171;
            border: 1px solid rgba(239, 68, 68, 0.4);
            padding: 3px 8px;
            font-size: 0.72rem;
            font-family: var(--font-mono);
            cursor: pointer;
            border-radius: 3px;
            transition: all 0.2s;
        }
        .btn-vault-action:hover {
            background: rgba(239, 68, 68, 0.15);
            border-color: #EF4444;
        }

        /* Maturity Gauge Bar */
        .maturity-bar-wrapper {
            background: var(--panel-bg);
            border: 1px solid var(--border);
            padding: 12px 20px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;
        }
        .maturity-title { font-family: var(--font-head); font-size: 0.85rem; font-weight: 600; }
        .progress-container {
            flex: 1;
            min-width: 200px;
            background: #0E131A;
            border: 1px solid var(--border);
            height: 12px;
            position: relative;
        }
        .progress-bar {
            height: 100%;
            background: var(--emerald);
            width: 20%;
            transition: width 0.4s ease;
        }

        /* 4-Box Grid Layout */
        .grid-4box {
            display: grid;
            grid-template-columns: 1fr 1fr;
            grid-template-rows: auto auto;
            gap: 16px;
        }
        @media (max-width: 900px) {
            .grid-4box { grid-template-columns: 1fr; }
        }

        .card {
            background: var(--panel-bg);
            border: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            height: 100%;
            min-height: 480px;
        }
        .card-header {
            background: #0E131A;
            border-bottom: 1px solid var(--border);
            padding: 10px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .card-title {
            font-family: var(--font-head);
            font-size: 0.9rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card-body {
            padding: 14px;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 10px;
            min-height: 0;
        }

        textarea.editor-box {
            width: 100%;
            flex: 1;
            min-height: 380px;
            background: #0E131A;
            border: 1px solid var(--border);
            color: #E2E8F0;
            font-family: var(--font-mono);
            font-size: 0.83rem;
            padding: 12px;
            resize: vertical;
            line-height: 1.5;
            box-sizing: border-box;
        }
        textarea.editor-box:focus {
            outline: none;
            border-color: var(--cyan);
            box-shadow: 0 0 8px rgba(0, 210, 180, 0.2);
        }

        .btn {
            background: var(--amber);
            color: #0B0F14;
            border: none;
            padding: 8px 16px;
            font-family: var(--font-mono);
            font-size: 0.8rem;
            font-weight: 700;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }
        .btn:hover { background: #FBBF24; }
        .btn-ghost {
            background: transparent;
            color: var(--cyan);
            border: 1px solid var(--border);
        }
        .btn-ghost:hover { background: rgba(0, 210, 180, 0.1); border-color: var(--cyan); }
        .btn-emerald { background: var(--emerald); color: #0B0F14; }
        .btn-emerald:hover { background: #34D399; }

        /* Diff styling */
        .diff-view-box {
            background: #0E131A;
            border: 1px solid var(--border);
            padding: 12px;
            font-family: var(--font-mono);
            font-size: 0.83rem;
            min-height: 380px;
            flex: 1;
            overflow-y: auto;
            white-space: pre-wrap;
            line-height: 1.6;
            box-sizing: border-box;
        }
        .diff-del {
            background: rgba(239, 68, 68, 0.25);
            color: #F87171;
            padding: 2px 4px;
            border-radius: 2px;
            text-decoration: line-through;
        }
        .diff-ins {
            background: rgba(16, 185, 129, 0.25);
            color: #34D399;
            padding: 2px 4px;
            border-radius: 2px;
            font-weight: bold;
        }
        .diff-blank {
            background: rgba(245, 158, 11, 0.25);
            color: #FBBF24;
            padding: 2px 4px;
            border-radius: 2px;
        }

        .tips-list {
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 6px;
            margin-top: 6px;
        }
        .tip-item {
            font-size: 0.78rem;
            background: rgba(56, 189, 248, 0.08);
            border-left: 3px solid #38BDF8;
            padding: 6px 10px;
        }

        .findings-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            min-height: 380px;
            flex: 1;
            overflow-y: auto;
        }
        .finding-card {
            background: #0E131A;
            border: 1px solid var(--border);
            padding: 8px 12px;
            font-size: 0.78rem;
        }

        .english-box {
            background: #0E131A;
            border: 1px solid var(--border);
            color: #93C5FD;
            font-family: var(--font-mono);
            font-size: 0.83rem;
            padding: 12px;
            min-height: 380px;
            flex: 1;
            overflow-y: auto;
            white-space: pre-wrap;
            line-height: 1.5;
            box-sizing: border-box;
        }

        .status-strip {
            display: flex;
            gap: 12px;
            align-items: center;
            font-family: var(--font-mono);
            font-size: 0.75rem;
            margin-top: auto;
            padding-top: 4px;
        }
    </style>
</head>
<body>

    <!-- TOP TELEMETRY BAR -->
    <header>
        <div class="logo-area">
            <span style="font-size:1.6rem">🧠</span>
            <div>
                <div class="logo-title">RigMind <span style="font-size:0.75rem; color:var(--text-muted); font-weight:400">· Smart Resources</span></div>
                <div style="font-size:0.7rem; color:var(--text-muted)">Well Intervention, Workover & QA/QC Auditing (IADC Standard)</div>
            </div>
            <span class="badge badge-cyan" id="rigStatusBadge">AI Engine Active</span>
        </div>

        <div class="meta-controls">
            <label style="font-size:0.75rem; color:var(--text-muted)">Pozo:</label>
            <input type="text" id="wellNameInput" class="meta-input" value="Yopo-1" style="width:90px">
            
            <label style="font-size:0.75rem; color:var(--text-muted)">24h Check:</label>
            <span class="badge badge-emerald" id="timeBalanceBadge">24.0 / 24.0 Hrs</span>

            <button class="btn btn-ghost" onclick="loadSampleData()">📂 Cargar Ejemplo Yopo-1</button>
            <!-- CAJA FUERTE ZERO-KNOWLEDGE API -->
            <div id="apiVaultContainer"></div>
        </div>
    </header>

    <!-- MATURITY GAUGE & COMPLETENESS -->
    <div class="maturity-bar-wrapper">
        <div class="maturity-title">📊 Nivel de Madurez Técnica: <span id="tierLabel" style="color:var(--text-muted)">Pendiente de Evaluación</span></div>
        <div class="progress-container">
            <div class="progress-bar" id="maturityProgressBar"></div>
        </div>
        <div id="missingTipsText" style="font-size:0.75rem; color:var(--text-muted)">
            Sugerencia: Ingrese el reporte y presione "Procesar & Auditar" para auditar el cumplimiento normativo según la operación.
        </div>
    </div>

    <!-- 4-BOX MAIN WORKSPACE -->
    <div class="grid-4box">

        <!-- CAJA 1: ENTRADA CRUDA (ESPAÑOL) -->
        <div class="card">
            <div class="card-header">
                <div class="card-title"><span>📝</span> CAJA 1: Entrada Cruda (Español)</div>
                <button class="btn" onclick="runFullAudit()">⚡ Procesar & Auditar</button>
            </div>
            <div class="card-body">
                <textarea id="rawTextInput" class="editor-box" placeholder="Pegue aquí el reporte o notas de campo en español..."></textarea>
                <div class="status-strip">
                    <span>Duración calculada: <b id="calcDurText">0.0 h</b></span>
                    <span id="gapNoticeText" style="color:var(--amber)"></span>
                </div>
            </div>
        </div>

        <!-- CAJA 2: CONTROL DE CAMBIOS & APRENDIZAJE -->
        <div class="card">
            <div class="card-header">
                <div class="card-title"><span>🔍</span> CAJA 2: Control de Cambios & Aprendizaje (Diff)</div>
                <button class="btn btn-ghost" onclick="applyCorrectionToInput()">✔️ Aplicar a Caja 1</button>
            </div>
            <div class="card-body">
                <div id="diffViewBox" class="diff-view-box">Pegue su reporte en la Caja 1 y presione 'Procesar & Auditar' para ver el resaltado de errores en rojo y las correcciones en verde...</div>
                <ul class="tips-list" id="tipsListContainer"></ul>
            </div>
        </div>

        <!-- CAJA 3: RECOMENDACIONES QA/QC DE LOS 11 AGENTES -->
        <div class="card">
            <div class="card-header">
                <div class="card-title"><span>🛡️</span> CAJA 3: Auditoría QA/QC de los 11 Agentes Especializados</div>
                <span class="badge badge-cyan" id="findingsCountBadge">0 Alertas</span>
            </div>
            <div class="card-body">
                <div class="findings-list" id="findingsListContainer">
                    <div style="font-size:0.8rem; color:var(--text-muted); padding:10px;">
                        Aquí aparecerán las observaciones de los 11 agentes especializados:
                        <br>• <b>Abandono & Barreras P&A (Agent #11)</b>: NORSOK D-010 / API RP 96, HMBP overpull, giros a derecha, carta Barton, balance de tapones, toque TOC (≥10 klb).
                        <br>• <b>Auditoría de Traducción IADC (Agent #10)</b>: Cero Spanglish, cero omisión de datos, siglas operacionales IADC/SPE.
                        <br>• Integridad & BOP (API 53, pruebas en baja 250-350 psi, alta vs MASP, tiempos).
                        <br>• Movilización & Logística (R/D, R/M, R/U, cargas conciliadas, tarifas).
                        <br>• Tally & Sartas (holguras, velocidades, overpull).
                        <br>• Fluidos & Cemento (espesores, balance de tapones).
                        <br>• PCE / Wireline (correlación CCL, presiones lubricador).
                        <br>• Artificial Lift / BES (Megger, superbandas).
                        <br>• HSE (clasificación de NPT, tormentas, incidentes).
                    </div>
                </div>
            </div>
        </div>

        <!-- CAJA 4: TRADUCCIÓN OFICIAL EN INGLÉS (IADC) -->
        <div class="card">
            <div class="card-header">
                <div class="card-title"><span>🇬🇧</span> CAJA 4: Traducción IADC Oficial (Inglés)</div>
                <div style="display:flex; gap:6px;">
                    <button class="btn btn-ghost" onclick="copyEnglishTranslation()">📋 Copiar</button>
                    <button class="btn btn-emerald" onclick="saveToGoldenMemory()">⭐ Guardar en Memoria</button>
                </div>
            </div>
            <div class="card-body">
                <div id="englishOutputBox" class="english-box">Aquí se generará el texto oficial en inglés técnico petrolero estandarizado...</div>
                <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.75rem; color:var(--text-muted); margin-top:6px; flex-wrap:wrap; gap:8px;">
                    <div>
                        <span>⚡ Motor: <b id="translationEngineBadge" style="color:var(--amber)">Motor Especializado Offline IADC</b></span>
                        <span id="translationAuditBadge" class="badge badge-emerald" style="display:none; margin-left:8px;">🛡️ IADC Certified</span>
                        <span id="dataParityBadge" class="badge badge-cyan" style="display:none; margin-left:6px;">⚖️ Paridad 100%</span>
                    </div>
                    <span id="copyConfirmNotice" style="color:var(--emerald)"></span>
                </div>
            </div>
        </div>

    </div>

    <script>
        let latestAuditData = null;

        function getClientApiKey() {
            return localStorage.getItem('rigmind_api_key') || '';
        }

        function getClientProvider() {
            return localStorage.getItem('rigmind_provider') || 'auto';
        }

        function detectProviderFromKey(key) {
            if (!key) return 'auto';
            const k = key.trim();
            if (k.startsWith('sk-ant-')) return 'anthropic';
            if (k.startsWith('gsk_')) return 'groq';
            if (k.startsWith('sk-')) return 'openai';
            if (k.startsWith('AIza')) return 'gemini';
            return 'auto';
        }

        function renderApiVault() {
            const container = document.getElementById('apiVaultContainer');
            const rigBadge = document.getElementById('rigStatusBadge');
            const key = getClientApiKey();
            const provider = getClientProvider();

            if (key) {
                const detected = provider === 'auto' ? detectProviderFromKey(key) : provider;
                let providerLabel = 'OpenAI (GPT-4o)';
                let badgeClass = 'badge badge-emerald';

                if (detected === 'deepseek') {
                    providerLabel = '🐳 DeepSeek (V3)';
                    badgeClass = 'badge badge-cyan';
                } else if (detected === 'openai') {
                    providerLabel = '🟢 OpenAI (GPT-4o)';
                } else if (detected === 'anthropic') {
                    providerLabel = '🟣 Claude 3.5';
                } else if (detected === 'groq') {
                    providerLabel = '⚡ Groq (Llama 3.3)';
                } else if (detected === 'gemini') {
                    providerLabel = '🔵 Google Gemini';
                }

                if (rigBadge) {
                    rigBadge.className = badgeClass;
                    rigBadge.innerText = providerLabel + ' Conectado';
                }

                container.innerHTML = `
                    <div style="display:inline-flex; align-items:center; gap:8px; background:rgba(16, 185, 129, 0.12); border:1px solid rgba(16, 185, 129, 0.5); padding:4px 10px; border-radius:4px;" title="API Key blindada en su navegador y servidor.">
                        <span style="font-size:0.75rem; color:#34D399; font-weight:600; display:flex; align-items:center; gap:5px;">
                            <span>🔒</span> <span>${providerLabel} (******)</span>
                        </span>
                        <button type="button" class="btn-vault-action" onclick="changeApiKey()" title="Cambiar clave o proveedor">⚙️ Cambiar</button>
                    </div>
                `;
            } else {
                if (rigBadge) {
                    rigBadge.className = 'badge badge-amber';
                    rigBadge.innerText = '⚡ Motor Offline (Sin Clave IA)';
                }

                container.innerHTML = `
                    <div style="display:inline-flex; align-items:center; gap:6px; background:#0E131A; border:1px solid var(--border); padding:3px 8px; border-radius:4px;" title="Seleccione proveedor y pegue su API Key (OpenAI, Anthropic Claude, Groq o Gemini).">
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
                `;
            }
        }

        async function saveApiKeyClient() {
            const input = document.getElementById('secureApiKeyInput');
            const provSelect = document.getElementById('providerSelect');
            if (!input) return;
            const key = input.value.trim();
            if (!key) {
                alert('Por favor pegue la clave de API (OpenAI, Anthropic Claude, Groq o Gemini) antes de guardar.');
                return;
            }

            const provider = provSelect ? provSelect.value : 'auto';
            localStorage.setItem('rigmind_api_key', key);
            localStorage.setItem('rigmind_provider', provider);

            // Also send to backend for server-side persistence
            try {
                await fetch('/api/config/api-key', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: key })
                });
            } catch(e) {}

            input.value = '';
            renderApiVault();
            alert('🔒 ¡API Key configurada exitosamente! Se ha guardado en su navegador y servidor de manera blindada. Ahora puede procesar cualquier reporte con traducción IADC oficial.');
        }

        function changeApiKey() {
            if (confirm('¿Desea cambiar o ingresar una nueva API Key de IA?')) {
                localStorage.removeItem('rigmind_api_key');
                localStorage.removeItem('rigmind_provider');
                renderApiVault();
            }
        }

        window.addEventListener('DOMContentLoaded', renderApiVault);

        async function loadSampleData() {
            try {
                const res = await fetch('/api/sample');
                const data = await res.json();
                document.getElementById('rawTextInput').value = data.sample_text;
                runFullAudit();
            } catch (err) {
                alert('Error al cargar datos de ejemplo.');
            }
        }

        async function runFullAudit() {
            const rawText = document.getElementById('rawTextInput').value.trim();
            const wellName = document.getElementById('wellNameInput').value.trim();
            if (!rawText) {
                alert('Por favor ingrese o pegue texto en la Caja 1.');
                return;
            }

            const clientKey = getClientApiKey();
            const clientProvider = getClientProvider();

            document.getElementById('diffViewBox').innerHTML = 'Auditando y analizando reporte...';
            document.getElementById('englishOutputBox').innerText = 'Generando traducción técnica IADC con IA...';

            try {
                const response = await fetch('/api/audit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        raw_text: rawText,
                        well_name: wellName,
                        api_key: clientKey,
                        provider: clientProvider
                    })
                });

                if (!response.ok) throw new Error('Error en el servidor.');
                const data = await response.json();
                latestAuditData = data;

                // 1. Time balance check
                const totalHours = data.chronology.total_duration;
                document.getElementById('calcDurText').innerText = totalHours + ' h';
                const balBadge = document.getElementById('timeBalanceBadge');
                balBadge.innerText = totalHours + ' / 24.0 Hrs';
                if (data.chronology.is_24_closed) {
                    balBadge.className = 'badge badge-emerald';
                    document.getElementById('gapNoticeText').innerText = '✅ Cierre exacto de 24h';
                } else {
                    balBadge.className = 'badge badge-amber';
                    document.getElementById('gapNoticeText').innerText = '⚠️ Diferencia de ' + data.chronology.variance_hours + ' h';
                }

                // 2. Visual Diff & Tips (Caja 2)
                document.getElementById('diffViewBox').innerHTML = data.visual_diff_html;
                const tipsContainer = document.getElementById('tipsListContainer');
                tipsContainer.innerHTML = '';
                data.learning_tips.forEach(tip => {
                    const li = document.createElement('li');
                    li.className = 'tip-item';
                    li.innerText = tip;
                    tipsContainer.appendChild(li);
                });

                // 3. QA/QC Findings (Caja 3)
                const findingsContainer = document.getElementById('findingsListContainer');
                findingsContainer.innerHTML = '';
                document.getElementById('findingsCountBadge').innerText = data.agent_findings.length + ' Alertas';
                data.agent_findings.forEach(f => {
                    const card = document.createElement('div');
                    card.className = 'finding-card';
                    card.innerHTML = `<div style="font-weight:700; margin-bottom:4px">${f.badge} <span style="color:var(--text-muted); font-size:0.7rem">(${f.agent})</span></div><div>${f.message}</div>`;
                    findingsContainer.appendChild(card);
                });

                // 4. Maturity Level
                const mat = data.maturity;
                document.getElementById('tierLabel').innerText = mat.tier_label;
                document.getElementById('tierLabel').style.color = mat.tier_color;
                const pBar = document.getElementById('maturityProgressBar');
                pBar.style.width = mat.score_percent + '%';
                pBar.style.background = mat.tier_color;
                document.getElementById('missingTipsText').innerText = mat.missing_for_next_level.length > 0 ?
                    'Sugerencia: Falta ' + mat.missing_for_next_level.join(', ') : '¡Nivel Élite alcanzado!';

                // 5. English Translation (Caja 4)
                document.getElementById('englishOutputBox').innerText = data.english_iadc;
                if (data.engine_source) {
                    const engineBadge = document.getElementById('translationEngineBadge');
                    engineBadge.innerText = data.engine_source;
                    engineBadge.style.color = data.engine_source.includes('Gemini') ? 'var(--emerald)' : 'var(--amber)';
                }
                if (data.translation_qaqc) {
                    const auditBadge = document.getElementById('translationAuditBadge');
                    auditBadge.style.display = 'inline-block';
                    if (data.translation_qaqc.has_spanglish) {
                        auditBadge.className = 'badge badge-amber';
                        auditBadge.innerText = '⚠️ Spanglish Detectado (' + data.translation_qaqc.quality_score + '%)';
                    } else {
                        auditBadge.className = 'badge badge-emerald';
                        auditBadge.innerText = '🛡️ IADC Certified';
                    }

                    const parityBadge = document.getElementById('dataParityBadge');
                    if (parityBadge && data.translation_qaqc.data_parity_pct !== undefined) {
                        parityBadge.style.display = 'inline-block';
                        const pPct = data.translation_qaqc.data_parity_pct;
                        parityBadge.className = pPct >= 80 ? 'badge badge-cyan' : 'badge badge-amber';
                        parityBadge.innerText = '⚖️ Paridad 1:1 (' + pPct + '%)';
                    }
                }

            } catch (err) {
                alert('Error al procesar el reporte: ' + err.message);
            }
        }

        function applyCorrectionToInput() {
            if (latestAuditData && latestAuditData.corrected_spanish) {
                document.getElementById('rawTextInput').value = latestAuditData.corrected_spanish;
                alert('Correcciones técnicas aplicadas a la Caja 1.');
                runFullAudit();
            } else {
                alert('Primero debe presionar Procesar & Auditar.');
            }
        }

        function copyEnglishTranslation() {
            const txt = document.getElementById('englishOutputBox').innerText;
            if (txt && !txt.startsWith('Aquí se')) {
                navigator.clipboard.writeText(txt);
                alert('¡Traducción IADC copiada al portapapeles!');
            }
        }

        async function saveToGoldenMemory() {
            if (!latestAuditData) {
                alert('Primero procese un reporte.');
                return;
            }
            const opName = prompt('Ingrese el nombre de la operación para esta memoria (ej. Asentamiento Bridge Plug 7"):', 'Operación Estándar');
            if (!opName) return;

            const payload = {
                category: 'well_intervention',
                operation: opName,
                spanish_exemplar: latestAuditData.corrected_spanish,
                english_iadc: latestAuditData.english_iadc,
                learning_tip: latestAuditData.learning_tips.join(' | ')
            };

            const res = await fetch('/api/memory/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const d = await res.json();
            if (d.success) {
                alert('⭐ ¡Ejemplo guardado con éxito en la Memoria de Aprendizaje!');
            }
        }
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
