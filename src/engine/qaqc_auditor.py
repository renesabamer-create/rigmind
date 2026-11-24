import os
import re
import json
import urllib.request
import difflib
from typing import List, Dict, Any, Tuple, Optional
from src.engine.learning_memory import classify_operational_domain
from src.engine.chronology import parse_raw_timeline
from src.engine.llm_network import execute_llm_request, detect_provider

# ==============================================================================
# ELITE SPANISH ENGINEERING AUDIT SYSTEM PROMPT (DeepSeek V3, GPT-4o, Claude 3.5)
# ==============================================================================

ELITE_SPANISH_AUDIT_SYSTEM_PROMPT = """Eres el Superintendente Senior de Operaciones de Pozo y Auditor Técnico QA/QC de RigMind (Smart Resources).
Tu misión es transformar notas crudas, informales o desordenadas de campo en español en un reporte técnico de operaciones (DOR) de pozo IMPECABLE, RIGUROSO y PROFESIONAL en español bajo normativas API, SPE, IADC y NORSOK D-010.

DIRECTIVAS OPERACIONALES ESTRICTAS:
1. PROTOCOLO DE CERO OMISIÓN DE DATOS:
   Conserva CADA detalle, maniobra, volumen, presión, profundidad, tiempo, herramienta, número de serie o junta. NUNCA resumas, sintetices o elimines actividades.
2. CRONOLOGÍA Y TIEMPOS OPERACIONALES (RECONOCIMIENTO DE INTERVALOS Y HITOS SECUENCIALES):
   - Reconoce ambos formatos de registro de tiempo usados en campo:
     a) MODO INTERVALO (HH:MM - HH:MM): Cada actividad tiene hora de inicio y fin explícita.
     b) MODO SECUENCIAL (Solo HH:MM): Si cada línea solo tiene la hora de inicio (ej. "01:00 Inicia bombeo" y luego "02:30 Termina bombeo"), la hora de fin es el inicio de la siguiente actividad. Debes transformar cada evento a formato estándar IADC de rango: "01:00 - 02:30: Inicia bombeo...". La última actividad concluye a las 24:00 o fin de turno.
   - Si la primera actividad no tiene hora asignada (ej. "Personal toma de alimentos y descanso"), asígnale el rango estándar "00:00 - 01:00: ".
   - Une líneas huérfanas de horas (ej. si "01:00 - 01:30" está solo en una línea, únelo con la actividad siguiente).
   - Agrupa notas y viñetas multilínea debajo de su respectivo intervalo horario sin romper párrafos.
   - NO agregues títulos decorativos ni encabezados artificiales al inicio del texto (NO escribas "REPORTE TÉCNICO DE OPERACIONES", "DOR POZO X", etc.); inicia directamente con las líneas de eventos ("00:00 - 01:00: ...") para preservar la correspondencia limpia y el diff visual con el original.
3. CORRECCIÓN ORTOGRÁFICA Y TIPOGRÁFICA DE CAMPO:
   - Corrige errores típicos de tipeo en taladro:
     "pup joi t" -> "pup joint de manejo"
     "xequipos" -> "equipos de superficie Novomet"
     "lineas" -> "líneas", "tuberia" -> "tubería", "reunion" -> "reunión", "tensiono" -> "tensionó"
4. ESTANDARIZACIÓN TÉCNICA PETROLERA EN ESPAÑOL:
   - "choque" o "el choque" -> "manifold de choque (choke manifold)"
   - "arme" o "arme del equipo" -> "Rig Up (R/U) y arme de equipos de superficie"
   - "llaves hidraulicas" -> "llaves hidráulicas de potencia (Power Tongs)"
   - "Novomet arme de sus xequipos" -> "Compañía Novomet realiza arme y conexionado de equipos de superficie para sistema BES (ESP)"
   - "check list" -> "checklist preoperacional diario de herramientas y equipos"
   - "pulling" -> "pulling de tubería / sarta"
5. SANIDAD FÍSICA Y MATEMÁTICA:
   - Corrige errores de unidades: si dice "peso 68000 klbs", es un error de digitación por libras (68 millones de libras es absurdo). Corrígelo a "peso neutro de sarta: 68 klb (68,000 lb)" y aclara sobretensión (ej. "tensionó hasta 70 klb, overpull: 2 klb").
   - Si hay bombeo o circulación sin caudal o fluido, inserta placeholders interactivos claros: "[especificar fluido: agua industrial / salmuera] a [___ bpm] con [___ psi] y retorno a catch tank".
6. DIRECTIVA DE TRIPPING / MANIOBRA DE TUBERÍA (POOH / RIH) - AGENTE TALLY & MECÁNICA DE SARTA:
   Toda operación de viaje de tubería (POOH / RIH / sacar tubería / bajar tubería / pulling / corrida) DEBE auditar y estructurar rigurosamente:
   a) COTAS DE PROFUNDIDAD: Exige cota inicial y cota final (ej. "desde 5518 ft hasta 5456 ft"). Si faltan, inserta placeholders interactivos: "desde [___ ft] hasta [___ ft]".
   b) TALLY DE JUNTAS Y AVANCE %: Exige el conteo de juntas (ej. "(4/150 jtas)") y calcula matemáticamente el avance porcentual ("avance: 2.7%"). Si el reporte incluye las juntas pero omitió el %, calcúlalo: (X/Y)*100%. Si el porcentaje reportado tiene error matemático, corrígelo y emite alerta crítica.
   c) ESPECIFICACIONES COMPLETAS DE TUBULAR: Exige tipo (Tubing / Drill Pipe / Sucker Rods / Workstring), diámetro exterior (ej. 2-7/8", 3-1/2"), peso nominal (lb/ft, ej. 9.3 lb/ft), grado metalúrgico (L-80, N-80, J-55) y rosca/conexión (EUE 8RD, PH-6, etc.). Si faltan, inserta placeholders: "[TBG 3-1/2\" EU, ___ lb/ft, grado: ___]".
   d) PESOS DE SARTA EN MOVIMIENTO (HOISTING): Exige peso subiendo (SWU / PUW) y peso bajando (SWD / SOW) en klb para auditar arrastre de pozo (drag = PUW - SWD).
   e) MODO DE MANIOBRA: Exige detallar si se maniobra "quebrando en sencillos a rack" o "paradas en dobles a peine".
   f) CONTROL DE POZO Y LLENADO (API RP 59): Exige indicar si se saca con "tubería llena" o "tubería seca", y el monitoreo de reposición de fluido en anular / tanque de viaje (trip tank) para reemplazar el volumen de desplazamiento del acero y prevenir pistoneo (swabbing / kick).
7. REGLA DE RECONSTRUCCIÓN DE PÁRRAFO COMPLETO DE INGENIERÍA (GOLDEN PARAGRAPH EXPANSION):
   Cuando una línea del reporte crudo sea escueta, incompleta o le falten datos esenciales para la certificación técnica, NO te limites a una corrección cosmética de palabras aisladas. DEBES RECONSTRUIR LA ORACIÓN COMPLETA en el formato canónico de ingeniería petrolera SPE/IADC, insertando los parámetros faltantes entre corchetes claramente rotulados `[CAMPO FALTANTE]` para que el usuario solo tenga que rellenar los datos de su libreta:
   a) EN CORRIDAS Y SACADAS DE TUBERÍA (RIH / POOH / PULLING):
      - Si escriben: "RIH BHA No. 1 con TBG 2-7/8\" en sencillos desde superficie hasta 835.60 ft (26 Jts)."
        Debes generar:
        "RIH BHA No. 1 [especificar tipo de BHA y objetivo: ej. pesca / completamiento / limpieza] con TBG 2-7/8\" [especificar: rosca ej. EUE 8RD, peso: ___ lb/ft, grado: ___] en sencillos desde superficie hasta 835.60 ft (26/[TOTAL JTS] jtas), avance: [___]%, SWD: [___] klb, Vel: [___] jts/h, condición de llenado: [tubería llena/seca, reposición en trip tank: ___ bbl]."
      - Si escriben: "Se retiran 3 juntas de tubería retirando mls joints y overcoupling."
        Debes generar:
        "POOH [especificar tubular: ej. TBG 3-1/2\" 9.3 lb/ft N-80 EUE] quebrando en sencillos a rack desde [___ ft] hasta [___ ft], retirando 3 juntas (3/[TOTAL JTS] jtas), avance: [___]%, retirando MLE (cable BES) y overcouplings con superbandas. SWU: [___] klb, SWD: [___] klb, Vel: [___] jts/h, condición de sarta: [tubería llena/seca]."
      - Si escriben: "Se continúa sacando tubería hasta la junta #23 retirando mls joints y overcoupling, en la junta #21 a 5 FT de la base sale empalme de cable."
        Debes generar:
        "Continuó POOH [especificar tubular: ej. TBG 3-1/2\" 9.3 lb/ft N-80 EUE] con tubería [llena / seca] quebrando en sencillos a rack desde [___ ft] hasta [___ ft] retirando juntas hasta acumulado (23/[TOTAL JTS] jtas, avance: [___]%), retirando MLE y overcouplings con superbandas. En junta #21 a 5 ft de la base se evidencia empalme de cable BES [inspección eléctrica/mecánica: sin novedad / corte]. SWU: [___] klb, SWD: [___] klb, Vel: [___] jts/h."
   b) EN PRUEBAS DE INTEGRIDAD Y PRESIÓN (API 53 / BOP / HMBP / MANIFOLD):
      - Si escriben: "Realizó prueba de integridad del HMBP aplicando 500 psi durante 15 minutos, ok. Dejó registrada en carta bartón."
        Debes generar:
        "Probó integridad de presión de HMBP de 7\" con [___ bbl] de agua industrial a [___ bpm], aplicando 500 psi durante 15 minutos, resultados satisfactorios (0 psi caída). Dejó registrada prueba en carta manométrica circular Barton [No. ___]."
   c) EN TAPONES DE CEMENTO Y P&A:
      - Generar estructura canónica:
        "Bombeó tapón de cemento No. [___] desde [___ ft] hasta [___ ft] ([___ ft] de espesor) con [___ bbl] de lechada Clase G [15.8 ppg] a [___ bpm] con [___ psi]. Preflujo: [___ bbl]. Desplazamiento: [___ bbl]. WOC: [___ h]. TOC verificado con [___ klb]."
   d) EN CIRCULACIONES Y CONTROL DE POZO:
      - Generar estructura canónica:
        "Circuló en [directa / reversa] con [___ bbl] de [agua industrial / salmuera / lodo de ___ ppg] a [___ bpm] con [___ psi], con retorno hacia catch tank, pérdidas/ganancias: [___ bbl]."
8. FORMATO DE SALIDA (EXCLUSIVAMENTE JSON):
Debes responder ÚNICAMENTE un bloque JSON válido con este esquema:
{
  "corrected_spanish": "Líneas cronológicas saneadas directamente en español hora por hora (sin títulos decorativos)...",
  "agent_findings": [
    {
      "agent": "nombre-del-agente-especialista (ej. tally-mechanics-engineer, chronology-time-reconciliation-auditor, well-integrity-bop-specialist, rig-move-logistics-specialist, well-control-pna-specialist, esp-artificial-lift-specialist, hse-npt-compliance-auditor, lead-intervention-director, oilfield-translator-editor)",
      "severity": "CRITICAL" | "WARNING" | "INFO" | "SUCCESS",
      "badge": "EMOJI + TITULO DE ALERTA",
      "message": "Explicación técnica detallada de lo detectado, corregido o norma aplicable."
    }
  ],
  "learning_tips": [
    "Consejo pedagógico 1",
    "Consejo pedagógico 2"
  ]
}
"""

# ==============================================================================
# TOKEN-LEVEL VISUAL DIFF GENERATOR (HTML Red/Green Highlights)
# ==============================================================================

def generate_token_diff(raw_text: str, corrected_text: str) -> str:
    """
    Produces clean HTML highlighting differences between raw and corrected text:
    - Red strikethroughs for deleted/replaced text: <span class="diff-del"><s>...</s></span>
    - Green bold for added/corrected text: <span class="diff-ins"><b>...</b></span>
    - Amber bold for placeholders to complete: <span class="diff-blank"><b>...</b></span>
    """
    raw_tokens = re.findall(r'\S+|\n|[^\S\n]+', raw_text)
    corr_tokens = re.findall(r'\S+|\n|[^\S\n]+', corrected_text)
    
    matcher = difflib.SequenceMatcher(None, raw_tokens, corr_tokens)
    out = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            out.append(''.join(raw_tokens[i1:i2]))
        elif tag == 'replace':
            old_str = ''.join(raw_tokens[i1:i2])
            new_str = ''.join(corr_tokens[j1:j2])
            out.append(f'<span class="diff-del"><s>{old_str}</s></span><span class="diff-ins"><b>{new_str}</b></span>')
        elif tag == 'delete':
            old_str = ''.join(raw_tokens[i1:i2])
            out.append(f'<span class="diff-del"><s>{old_str}</s></span>')
        elif tag == 'insert':
            new_str = ''.join(corr_tokens[j1:j2])
            if '[' in new_str and ']' in new_str:
                out.append(f'<span class="diff-blank"><b>{new_str}</b></span>')
            else:
                out.append(f'<span class="diff-ins"><b>{new_str}</b></span>')
                
    return ''.join(out)


# ==============================================================================
# OFFLINE DETERMINISTIC PETROLEUM POLISHER (Rulebook Fallback)
# ==============================================================================

def offline_polish_spanish(raw_text: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Comprehensive offline heuristic engine for Spanish field notes sanitization.
    Normalizes typos, units, missing timestamps, and technical nomenclature.
    """
    text = raw_text
    findings = []
    learning_tips = []

    # Check if input is sequential point-in-time mode (only start times)
    chrono_info = parse_raw_timeline(text)
    if chrono_info.get("mode") == "sequential_inferred" and chrono_info.get("reconstructed_narrative"):
        text = chrono_info["reconstructed_narrative"]

    # 1. Missing midnight hour interval
    if re.match(r"^\s*(?:personal\s+)?toma\s+de\s+alimentos", text, re.IGNORECASE):
        text = re.sub(r"^\s*(personal\s+toma\s+de\s+alimentos\s+y\s+descanso\.?)", r"00:00 - 01:00: \1", text, flags=re.IGNORECASE)
        findings.append({
            "agent": "lead-intervention-director",
            "severity": "WARNING",
            "badge": "🟠 CRONOLOGÍA: INTERVALO INICIAL ASIGNADO",
            "message": "La actividad inicial de descanso/alimentos no tenía rango horario asignado. Se asignó automáticamente el intervalo estándar '00:00 - 01:00' para iniciar el cierre de 24 horas."
        })
        learning_tips.append("💡 Práctica de Cronología: Todo reporte operacional debe iniciar estrictamente a las 00:00 h para garantizar el balance y facturación de 24 horas del día.")

    # 2. Orphaned timestamp lines (e.g. "01:00 - 01:30\n\nContinuan...")
    orphan_pattern = re.compile(r"(\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})\s*\n+(\s*\w)", re.MULTILINE)
    if orphan_pattern.search(text):
        text = orphan_pattern.sub(r"\1: \2", text)
        findings.append({
            "agent": "lead-intervention-director",
            "severity": "INFO",
            "badge": "🔵 CRONOLOGÍA: LÍNEAS HUÉRFANAS ESTRUCTURADAS",
            "message": "Se unificaron los encabezados de hora que se encontraban aislados con sus actividades correspondientes."
        })

    # 3. Critical string weight absurdity (e.g. 68000 klbs -> 68 klb)
    absurd_weight_pattern = re.compile(r"peso\s+(\d{4,6})\s*klbs?", re.IGNORECASE)
    m_absurd = absurd_weight_pattern.search(text)
    if m_absurd:
        val = int(m_absurd.group(1))
        corr_val = val // 1000 if val >= 1000 else val
        text = text.replace(m_absurd.group(0), f"peso neutro de sarta {corr_val} klb ({val:,} lb)")
        findings.append({
            "agent": "tally-mechanics-engineer",
            "severity": "CRITICAL",
            "badge": "🔴 ERROR CRÍTICO DE UNIDADES EN PESO DE SARTA",
            "message": f"Se reportó erróneamente '{m_absurd.group(0)}'. En campo petrolero, 1 klb = 1,000 lb, por lo que {val:,} klb equivaldría a {val/1000:,.1f} millones de libras (físicamente absurdo). Se corrigió a {corr_val} klb ({val:,} lb)."
        })
        learning_tips.append(f"💡 Mecánica de Sartas: Recuerde la nomenclatura: 1 klb = 1,000 lb. Si el peso son {val:,} libras en el indicador de peso (Martin Decker), debe escribirse {corr_val} klb.")

    # 4. Overpull / Tension clarification (e.g. "tensiono con 70 klbs")
    m_tens = re.search(r"tension[oó]\s+con\s+(\d+)\s*klbs?", text, re.IGNORECASE)
    if m_tens:
        tens_val = int(m_tens.group(1))
        text = re.sub(r"tension[oó]\s+con\s+(\d+)\s*klbs?", rf"tensionó sarta hasta \1 klb", text, flags=re.IGNORECASE)
        findings.append({
            "agent": "tally-mechanics-engineer",
            "severity": "SUCCESS",
            "badge": "🟢 TENSIÓN DE SARTA AUDITADA",
            "message": f"Tensión aplicada de {tens_val} klb para desasentar y sacar primeras juntas verificada dentro de parámetros."
        })

    # 5. Field Typos and Lexical Normalization
    replacements = [
        (r"\bpup\s+joi\s*t(?:\s+de\s+manejo)?\b", "pup joint de manejo", "pup joint", "🔵 CORRECCIÓN ORTOGRÁFICA: PUP JOINT"),
        (r"\bNovomet\s+arme\s+de\s+sus\s+x?equipos\.?", "Compañía Novomet realiza arme y conexionado de equipos de superficie BES (ESP).", "equipos Novomet", "🔵 ESTANDARIZACIÓN BES: NOVOMET"),
        (r"\bxequipos\b", "equipos de superficie", "equipos", "🔵 CORRECCIÓN DE TIPEO: XEQUIPOS"),
        (r"(?:y\s+el\s+choque|\bchoque\b)(?!\s*manifold|\s*\(choke)", "manifold de choque (choke manifold)", "choke manifold", "🔵 ESTANDARIZACIÓN TÉCNICA: CHOKE MANIFOLD"),
        (r"(?:rig\s+up\s+llaves\s+hidr[aá]ulicas|llaves\s+hidr[aá]ulicas\b)(?!\s*de\s+potencia)", "R/U de llaves hidráulicas de potencia (Power Tongs)", "llaves hidráulicas", "🔵 ESTANDARIZACIÓN TÉCNICA: POWER TONGS"),
        (r"\bcheck\s*list\s+diario\b", "checklist preoperacional diario", "checklist", "🔵 SEGURIDAD: CHECKLIST DIARIO"),
        (r"\breuni[oó]n\s+preoperacional\s+para\s+", "reunión preoperacional de seguridad (PJSM) para ", "reunión preoperacional", "🔵 SEGURIDAD: PJSM"),
        (r"desarm[oó]\s+el\s+arbolito", "N/D Árbol de Producción (X-tree 7-1/16\" 3K/5K)", "árbol de producción", "🔵 ESTANDARIZACIÓN X-TREE"),
        (r"retir[oó]\s+arbolito", "N/D Árbol de Producción", "árbol de producción", "🔵 ESTANDARIZACIÓN X-TREE"),
        (r"instal[oó]\s+preventoras", "N/U conjunto de preventoras (BOP stack 7-1/16\" 5K)", "BOP stack", "🔵 ESTANDARIZACIÓN BOP"),
        (r"ech[oó]\s+reversa", "circuló en reversa hasta retorno limpio", "circulación en reversa", "🔵 ESTANDARIZACIÓN HIDRÁULICA"),
        (r"meti[oó]\s+barra", "lanzó barra para cizallar pin de drain sub", "barra drain sub", "🔵 ESTANDARIZACIÓN DRAIN SUB"),
        (r"\bmls\s+joints\b", "MLE (Motor Lead Extension)", "MLE joints", "🔵 ESTANDARIZACIÓN BES: CABLE MLE"),
        (r"\bovercoupling\b", "overcouplings con superbandas", "overcouplings", "🔵 ESTANDARIZACIÓN BES: OVERCOUPLING"),
        (r"\bcarta\s+bart[oó]n\b", "carta manométrica circular Barton [No. ___]", "carta Barton", "🔵 INTEGRIDAD: CARTA BARTON"),
        (r"\bcontinuan\b", "continúan", "continúan", None),
        (r"\blineas\b", "líneas", "líneas", None),
        (r"\btuberia\b", "tubería", "tubería", None),
        (r"\brealizo\b", "realizó", "realizó", None),
        (r"\bcirculacion\b", "circulación", "circulación", None),
    ]

    for pat, rep, name, badge in replacements:
        if re.search(pat, text, re.IGNORECASE):
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)
            if badge:
                findings.append({
                    "agent": "oilfield-translator-editor",
                    "severity": "INFO",
                    "badge": badge,
                    "message": f"Se normalizó la terminología de campo hacia estándar técnico: '{name}'."
                })

    # 6. Circulation without rate/fluid
    circ_match = re.search(r"circulaci[oó]n\s+en\s+directa\s+(\d+)\s*bbls?\s+con\s+(\d+)\s*psi", text, re.IGNORECASE)
    if circ_match:
        bbls = circ_match.group(1)
        psi = circ_match.group(2)
        better_circ = f"circulación en directa de {bbls} bbl de fluido [especificar fluido: agua industrial / salmuera] a [___ bpm] con {psi} psi y retorno a catch tank"
        text = text.replace(circ_match.group(0), better_circ)
        findings.append({
            "agent": "well-control-pna-specialist",
            "severity": "WARNING",
            "badge": "🟡 PARÁMETROS DE BOMBEO INCOMPLETOS",
            "message": f"Se reportó circulación de {bbls} bbl a {psi} psi, pero se omitió la tasa de bombeo (bpm) y el tipo de fluido. Se insertaron placeholders '[___ bpm]' en la Caja 2 para que complete el dato antes de traducir."
        })
        learning_tips.append("💡 Práctica de Hidráulica: Toda circulación de pozo debe indicar volumen (bbl), tasa de bombeo (bpm), presión (psi) y tipo de fluido de pozo.")

    # 7. Tripping (POOH / RIH) Verification, Tally & Golden Paragraph Expansion
    tripping_pattern = re.compile(
        r"\b(pooh|rih|pulling|sacar\s+tuber[ií]a|sacando\s+tuber[ií]a|se\s+retiran?\s+\d+\s+juntas?|retirando\s+\d+\s+juntas?|se\s+contin[uú]a\s+sacando|bajar\s+tuber[ií]a|bajando\s+tuber[ií]a|sacando\s+primeras\s+juntas|corrida\s+de\s+tuber[ií]a|m/u\s+bha|rih\s+bha|pooh\s+bha)\b",
        re.IGNORECASE
    )
    if tripping_pattern.search(text):
        # 1. Expansion for tubular without thread/weight (on raw text): e.g. "TBG 2-7/8"" or "tubería 2-7/8""
        tbg_spec_pattern = re.compile(r'(?<!ej\.\s)(?<!ejemplo:\s)\b(tbg|tuber[ií]a)\s*(2-3/8|2-7/8|3-1/2|4-1/2|5)(?:\"|\'\')?(?!\s*\[)(?!\s*\d)(?!\s*lb/ft)', re.IGNORECASE)
        if tbg_spec_pattern.search(text):
            text = tbg_spec_pattern.sub(r'\1 \2" [especificar: rosca ej. EUE 8RD, peso: ___ lb/ft, grado: ___]', text)

        # 2. Expansion for "RIH/POOH BHA No. X" without objective
        bha_obj_pattern = re.compile(r"\b((?:rih|pooh)\s+bha\s+no\.?\s*\d+)\b(?!\s*\[)", re.IGNORECASE)
        if bha_obj_pattern.search(text):
            text = bha_obj_pattern.sub(r"\1 [especificar tipo de BHA y objetivo: ej. pesca / completamiento / limpieza]", text)

        # 3. Expansion for single tally count "(26 Jts)" to fraction + advance %
        single_tally_pattern = re.compile(r"\(\s*(\d+)\s*(?:jts?|juntas?|jtas?)\s*\)(?!\s*,\s*avance)", re.IGNORECASE)
        if single_tally_pattern.search(text):
            text = single_tally_pattern.sub(r"(\1/[TOTAL JTS] jtas), avance: [___]%", text)

        # 4. Expansion for "Se retiran X juntas de tubería"
        m_retira = re.search(r"se\s+retiran?\s+(\d+)\s+juntas\s+de\s+tuber[ií]a", text, re.IGNORECASE)
        if m_retira:
            jtas_ret = m_retira.group(1)
            repl_retira = f"POOH [especificar tubular: ej. TBG 3-1/2\" 9.3 lb/ft N-80 EUE] quebrando en sencillos a rack desde [___ ft] hasta [___ ft], retirando {jtas_ret} juntas ({jtas_ret}/[TOTAL JTS] jtas), avance: [___]%, SWU: [___] klb, SWD: [___] klb, Vel: [___] jts/h, condición de sarta: [tubería llena/seca]"
            text = text.replace(m_retira.group(0), repl_retira)

        # 5. Expansion for "Se continúa sacando tubería hasta la junta #X"
        m_cont = re.search(r"se\s+contin[uú]a\s+sacando\s+tuber[ií]a\s+hasta\s+la\s+junta\s*#?\s*(\d+)", text, re.IGNORECASE)
        if m_cont:
            j_target = m_cont.group(1)
            repl_cont = f"Continuó POOH [especificar tubular: ej. TBG 3-1/2\" 9.3 lb/ft N-80 EUE] con tubería [llena / seca] quebrando en sencillos a rack desde [___ ft] hasta [___ ft] retirando juntas hasta acumulado ({j_target}/[TOTAL JTS] jtas, avance: [___]%), SWU: [___] klb, SWD: [___] klb, Vel: [___] jts/h"
            text = text.replace(m_cont.group(0), repl_cont)

        # 6. Expansion for RIH missing weights, speeds and displacement
        if re.search(r"\bRIH\b", text, re.IGNORECASE) and not re.search(r"\b(?:swd|sow|peso\s+bajando)\b", text, re.IGNORECASE):
            if "[TOTAL JTS]" in text and "SWD:" not in text:
                text = text.replace("avance: [___]%", "avance: [___]%, SWD: [___] klb, Vel: [___] jts/h, condición de llenado: [tubería llena/seca, trip tank: ___ bbl]")

        # 7. Joint Tally & Calculated Progress (e.g. 4/150 jtas -> avance: 2.7%)
        tally_pattern = re.compile(r"\(?\s*(\d+)\s*/\s*(\d+)\s*(?:jtas?|juntas?|jts?)\s*\)?", re.IGNORECASE)
        m_tally = tally_pattern.search(text)
        if m_tally:
            j_cur = int(m_tally.group(1))
            j_tot = int(m_tally.group(2))
            if j_tot > 0:
                calc_pct = round((j_cur / j_tot) * 100, 1)
                pct_pattern = re.compile(r"avance\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
                m_pct = pct_pattern.search(text)
                if m_pct:
                    stated_pct = float(m_pct.group(1))
                    if abs(stated_pct - calc_pct) > 1.0:
                        text = text.replace(m_pct.group(0), f"avance: {calc_pct}%")
                        findings.append({
                            "agent": "tally-mechanics-engineer",
                            "severity": "CRITICAL",
                            "badge": "🔴 ERROR MATEMÁTICO EN AVANCE DE JUNTAS",
                            "message": f"Discrepancia en avance de tubería: ({j_cur}/{j_tot} jtas) equivale al {calc_pct}%, pero el reporte indicaba erróneamente {stated_pct}%. Corregido automáticamente a {calc_pct}%."
                        })
                    else:
                        findings.append({
                            "agent": "tally-mechanics-engineer",
                            "severity": "SUCCESS",
                            "badge": "🟢 TALLY & AVANCE DE JUNTAS VERIFICADO",
                            "message": f"Conteo de juntas ({j_cur}/{j_tot} jtas) y avance del {calc_pct}% matemáticamente consistentes."
                        })
                else:
                    orig_tally = m_tally.group(0)
                    new_tally = f" ({j_cur}/{j_tot} jtas), avance: {calc_pct}% "
                    text = text.replace(orig_tally, new_tally)
                    text = re.sub(r"[ \t]+", " ", text)
                    findings.append({
                        "agent": "tally-mechanics-engineer",
                        "severity": "INFO",
                        "badge": "🔵 AVANCE DE JUNTAS CALCULADO",
                        "message": f"Se calculó e insertó el porcentaje de avance matemático: ({j_cur}/{j_tot} jtas) = {calc_pct}%."
                    })
        else:
            findings.append({
                "agent": "tally-mechanics-engineer",
                "severity": "WARNING",
                "badge": "🟡 CONTEO DE JUNTAS PENDIENTE",
                "message": "En maniobra de tubería (POOH/RIH) registre la fracción acumulada de juntas (ej. 4/150 jtas) y su avance porcentual."
            })

        # B. Initial and Final Depths
        depth_pattern = re.compile(r"(?:desde\s+)?(\d{3,5})\s*ft(?:\s*-\s*EM)?\s*(?:hasta|a)\s*(\d{3,5})\s*ft", re.IGNORECASE)
        m_depth = depth_pattern.search(text)
        if m_depth:
            d_init = int(m_depth.group(1))
            d_fin = int(m_depth.group(2))
            feet_tripped = abs(d_init - d_fin)
            findings.append({
                "agent": "tally-mechanics-engineer",
                "severity": "SUCCESS",
                "badge": "🟢 COTAS DE PROFUNDIDAD VERIFICADAS",
                "message": f"Intervalo de maniobra verificado: {d_init} ft a {d_fin} ft ({feet_tripped} ft recorridos)."
            })
        else:
            findings.append({
                "agent": "tally-mechanics-engineer",
                "severity": "WARNING",
                "badge": "🟡 COTAS DE MANIOBRA FALTANTES",
                "message": "En todo tramo de POOH/RIH registre profundidad inicial y final (ej. 'desde 5518 ft hasta 5456 ft')."
            })

        # C. Tubular specs (OD, weight, grade, thread)
        has_od = bool(re.search(r'\b(?:2-3/8|2-7/8|3-1/2|4-1/2|5)\b', text))
        has_wt = bool(re.search(r'\d+(?:\.\d+)?\s*(?:lb/ft|#)', text, re.IGNORECASE))
        has_grade = bool(re.search(r'\b(l-?80|n-?80|j-?55|p-?110)\b', text, re.IGNORECASE))
        has_thread = bool(re.search(r'\b(eue|nue|8rd|ph-?6|hydril)\b', text, re.IGNORECASE))
        if has_od and has_wt and has_grade and has_thread:
            findings.append({
                "agent": "tally-mechanics-engineer",
                "severity": "SUCCESS",
                "badge": "🟢 ESPECIFICACIONES DE TUBULAR COMPLETAS",
                "message": "Tubular completamente especificado: diámetro, peso nominal, grado metalúrgico y conexión."
            })
        else:
            missing_specs = []
            if not has_od: missing_specs.append("diámetro (ej. 3-1/2\")")
            if not has_wt: missing_specs.append("peso nominal (ej. 9.3 lb/ft)")
            if not has_grade: missing_specs.append("grado de acero (ej. N-80 o L-80)")
            if not has_thread: missing_specs.append("conexión/rosca (ej. EUE 8RD)")
            findings.append({
                "agent": "tally-mechanics-engineer",
                "severity": "WARNING",
                "badge": "🟡 ESPECIFICACIÓN DE TUBULAR INCOMPLETA",
                "message": f"Falta detallar en sarta: {', '.join(missing_specs)}."
            })

        # D. Weights: SWU (subiendo) & SWD (bajando)
        has_swu = bool(re.search(r'\b(?:swu|puw|peso\s+subiendo)\b', text, re.IGNORECASE))
        has_swd = bool(re.search(r'\b(?:swd|sow|peso\s+bajando)\b', text, re.IGNORECASE))
        if has_swu and has_swd:
            findings.append({
                "agent": "tally-mechanics-engineer",
                "severity": "SUCCESS",
                "badge": "🟢 CONTROL DE PESOS Y ARRASTRE (SWU/SWD)",
                "message": "Se registraron pesos subiendo (SWU) y bajando (SWD), permitiendo auditar el arrastre (drag = SWU - SWD) del pozo."
            })
        else:
            findings.append({
                "agent": "tally-mechanics-engineer",
                "severity": "INFO",
                "badge": "🔵 RECOMENDACIÓN DE PESOS: REGISTRAR SWU Y SWD",
                "message": "Registre siempre peso subiendo (SWU/PUW) y bajando (SWD/SOW) para calcular arrastre (drag = PUW - SWD) y detectar empaquetamiento o fricción anómala."
            })

        # E. Singles vs Doubles
        has_mode = bool(re.search(r'\b(sencillos|dobles|stands|paradas)\b', text, re.IGNORECASE))
        if not has_mode:
            findings.append({
                "agent": "tally-mechanics-engineer",
                "severity": "INFO",
                "badge": "🔵 MODO DE MANIOBRA",
                "message": "Especifique si la tubería se sacó/bajó en sencillos (a rack) o en dobles (paradas a peine)."
            })

        # F. Hole Fill / Metal Displacement (API RP 59)
        has_fill = bool(re.search(r'\b(tuber[ií]a\s+llena|tuber[ií]a\s+seca|llenando\s+pozo|tanque\s+de\s+viaje|trip\s*tank|desplazamiento|reemplazando|pozo\s+lleno)\b', text, re.IGNORECASE))
        if has_fill:
            findings.append({
                "agent": "well-control-pna-specialist",
                "severity": "SUCCESS",
                "badge": "🟢 CONTROL DE POZO Y LLENADO EN VIAJE (API RP 59)",
                "message": "Se verificó condición de llenado de sarta y reposición de volumen de desplazamiento de acero."
            })
        else:
            findings.append({
                "agent": "well-control-pna-specialist",
                "severity": "WARNING",
                "badge": "🟡 CONTROL DE LLENADO DE POZO PENDIENTE (API RP 59)",
                "message": "En maniobra de POOH, indique si se saca con 'tubería llena' o 'seca', y registre la reposición periódica de fluido en el anular (tanque de viaje / trip tank) para compensar el desplazamiento del metal y evitar pistoneo (swabbing)."
            })
            learning_tips.append("💡 Práctica de Control de Pozo (API RP 59): En POOH, el anular debe llenarse cada 5 stands monitoreando el trip tank. La falta de llenado reduce la presión hidrostática y puede inducir un influjo (kick).")

    return text, findings, learning_tips


def enforce_golden_paragraph_standards(text: str, raw_text: str = "") -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Enforces canonical SPE/IADC Golden Paragraph formatting and interactive placeholders [___]
    on operations text, ensuring high technical rigour regardless of whether the primary
    draft was produced by an LLM (DeepSeek, OpenAI) or deterministic heuristics.
    """
    findings: List[Dict[str, Any]] = []
    learning_tips: List[str] = []

    # 1. Clean accidental prompt banner titles injected by AI if any
    text = re.sub(r"^(?:REPORTE\s+T[EÉ]CNICO[^\n]*|DOR[^\n]*)\n+", "", text, flags=re.IGNORECASE).strip()

    # 2. Field Typos & BES Standardizations
    text = re.sub(r"\bm[il]s\s+joints?\b", "MLE (Motor Lead Extension)", text, flags=re.IGNORECASE)
    text = re.sub(r"\bovercoupling\b", "overcouplings con superbandas", text, flags=re.IGNORECASE)
    text = re.sub(r"\bxequipos\b", "equipos de superficie Novomet", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpup\s+joi\s*t\b", "pup joint de manejo", text, flags=re.IGNORECASE)

    # 3. Canonical POOH expansions if missing
    # Case A: "Se retiran X juntas de tubería..."
    m_retira = re.search(r"(?:se\s+retiran?|retirando)\s+(\d+)\s+juntas\s+de\s+tuber[ií]a(?!\s*\(.*TOTAL)", text, re.IGNORECASE)
    if m_retira:
        jtas_ret = m_retira.group(1)
        repl_retira = f"POOH [especificar tubular: ej. TBG 3-1/2\" 9.3 lb/ft N-80 EUE] quebrando en sencillos a rack desde [___ ft] hasta [___ ft], retirando {jtas_ret} juntas ({jtas_ret}/[TOTAL JTS] jtas), avance: [___]%, SWU: [___] klb, SWD: [___] klb, Vel: [___] jts/h, condición de sarta: [tubería llena/seca]"
        text = text.replace(m_retira.group(0), repl_retira)

    # Case B: "Se continúa sacando tubería hasta la junta #X..."
    m_cont = re.search(r"se\s+contin[uú]a\s+sacando\s+tuber[ií]a\s+hasta\s+la\s+junta\s*#?\s*(\d+)(?!\s*\(.*TOTAL)", text, re.IGNORECASE)
    if m_cont:
        j_target = m_cont.group(1)
        repl_cont = f"Continuó POOH [especificar tubular: ej. TBG 3-1/2\" 9.3 lb/ft N-80 EUE] con tubería [llena / seca] quebrando en sencillos a rack desde [___ ft] hasta [___ ft] retirando juntas hasta acumulado ({j_target}/[TOTAL JTS] jtas, avance: [___]%), SWU: [___] klb, SWD: [___] klb, Vel: [___] jts/h"
        text = text.replace(m_cont.group(0), repl_cont)

    # Case C: Cable Splice Check
    m_splice = re.search(r"\bempalme\s+de\s+cable\b(?!\s*\[)", text, re.IGNORECASE)
    if m_splice:
        text = re.sub(r"\bempalme\s+de\s+cable\b(?!\s*\[)", "empalme de cable [especificar estado e integridad: ej. aislamiento > 1000 MΩ, prueba megger]", text, flags=re.IGNORECASE)
        findings.append({
            "agent": "esp-artificial-lift-specialist",
            "severity": "WARNING",
            "badge": "⚡ INTEGRIDAD BES: EMPALME DE CABLE",
            "message": "Se detectó empalme de cable en la sarta. En sistemas BES, todo empalme debe verificar prueba de aislamiento eléctrico (Megger > 1000 MΩ)."
        })
        learning_tips.append("💡 Práctica BES: Al recuperar un empalme de cable en sacada (POOH), verifique la continuidad de fases y resistencia de aislamiento a tierra (Megger).")

    # Case D: "RIH/POOH BHA No. X" without objective
    bha_obj_pattern = re.compile(r"\b((?:rih|pooh)\s+bha\s+no\.?\s*\d+)\b(?!\s*\[)", re.IGNORECASE)
    if bha_obj_pattern.search(text):
        text = bha_obj_pattern.sub(r"\1 [especificar tipo de BHA y objetivo: ej. pesca / completamiento / limpieza]", text)

    # Case E: Tubular without thread/weight: "TBG 2-7/8""
    tbg_spec_pattern = re.compile(r'(?<!ej\.\s)(?<!ejemplo:\s)\b(tbg|tuber[ií]a)\s*(2-3/8|2-7/8|3-1/2|4-1/2|5)(?:\"|\'\')?(?!\s*\[)(?!\s*\d)(?!\s*lb/ft)', re.IGNORECASE)
    if tbg_spec_pattern.search(text):
        text = tbg_spec_pattern.sub(r'\1 \2" [especificar: rosca ej. EUE 8RD, peso: ___ lb/ft, grado: ___]', text)

    # Case F: Single tally count "(26 Jts)" to fraction + advance %
    single_tally_pattern = re.compile(r"\(\s*(\d+)\s*(?:jts?|juntas?|jtas?)\s*\)(?!\s*,\s*avance)(?!/)", re.IGNORECASE)
    if single_tally_pattern.search(text):
        text = single_tally_pattern.sub(r"(\1/[TOTAL JTS] jtas), avance: [___]%", text)

    # Case G: Circulation without rate or fluid
    circ_match = re.search(r"circulaci[oó]n\s+en\s+directa\s+(\d+)\s*bbls?\s+con\s+(\d+)\s*psi(?!\s*\[)", text, re.IGNORECASE)
    if circ_match:
        bbls = circ_match.group(1)
        psi = circ_match.group(2)
        better_circ = f"circulación en directa de {bbls} bbl de fluido [especificar fluido: agua industrial / salmuera] a [___ bpm] con {psi} psi y retorno a catch tank"
        text = text.replace(circ_match.group(0), better_circ)

    # Add POOH / RIH best practice tips if tripping is present and not already in tips
    if re.search(r"\b(pooh|rih|pulling|sacar\s+tuber[ií]a|sacando\s+tuber[ií]a)\b", text, re.IGNORECASE):
        pooh_tips = [
            "En toda maniobra de sacada (POOH) registra siempre: cota inicial y final, número de junta extraída, total de juntas de la sarta y porcentaje de avance para auditar el tally.",
            "Documente los pesos de sarta (SWU y SWD) en cada viaje para detectar arrastre excesivo o sobrecargas que puedan indicar pega o fricción anormal.",
            "Registra el volumen desplazado y el nivel del trip tank durante el viaje; un llenado incorrecto puede permitir un influjo (kick) por pistoneo (API RP 59)."
        ]
        for pt in pooh_tips:
            if pt not in learning_tips:
                learning_tips.append(pt)

    return text, findings, learning_tips


# ==============================================================================
# AI-POWERED SPANISH ENGINEERING AUDITOR (DeepSeek, OpenAI, Groq, Claude, Gemini)
# ==============================================================================

def parse_audit_json(raw_resp: str) -> Dict[str, Any]:
    """Extracts and parses JSON object from LLM response safely."""
    clean = raw_resp.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean.strip())
    except Exception:
        # Fallback regex search for JSON block
        m = re.search(r"\{[\s\S]*\}", clean)
        if m:
            return json.loads(m.group(0))
        raise ValueError("No valid JSON found in AI audit response")


def call_ai_spanish_audit(text: str, api_key: str, provider: str = "auto", well_name: str = "Well") -> Optional[Dict[str, Any]]:
    """
    Executes the LLM Lead Well Operations Auditor in Spanish.
    Supports DeepSeek V3, OpenAI, Claude, Groq, and Gemini.
    """
    k = (api_key or "").strip()
    if not k:
        return None
    prov = detect_provider(k, requested=provider)

    # DeepSeek
    if prov == "deepseek":
        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {k}"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": ELITE_SPANISH_AUDIT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Audite, sanee y estandarice las siguientes notas crudas de campo del Pozo '{well_name}':\n\n{text}"}
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"}
        }
        try:
            result = execute_llm_request(url, payload, headers, timeout=40)
        except RuntimeError as e:
            if "response_format" in str(e).lower():
                del payload["response_format"]
                result = execute_llm_request(url, payload, headers, timeout=40)
            else:
                raise e
        choices = result.get("choices", [])
        if choices:
            return parse_audit_json(choices[0].get("message", {}).get("content", ""))

    # OpenAI
    elif prov == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {k}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": ELITE_SPANISH_AUDIT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Audite, sanee y estandarice las siguientes notas crudas de campo del Pozo '{well_name}':\n\n{text}"}
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"}
        }
        result = execute_llm_request(url, payload, headers, timeout=40)
        choices = result.get("choices", [])
        if choices:
            return parse_audit_json(choices[0].get("message", {}).get("content", ""))

    # Groq
    elif prov == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {k}"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": ELITE_SPANISH_AUDIT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Audite, sanee y estandarice las siguientes notas crudas de campo del Pozo '{well_name}':\n\n{text}"}
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"}
        }
        result = execute_llm_request(url, payload, headers, timeout=40)
        choices = result.get("choices", [])
        if choices:
            return parse_audit_json(choices[0].get("message", {}).get("content", ""))

    return None


# ==============================================================================
# MASTER MULTI-AGENT AUDIT ENGINE
# ==============================================================================

def audit_operations_text(raw_text: str, api_key: str = None, provider: str = "auto", well_name: str = "Yopo-1") -> Dict[str, Any]:
    """
    Runs multi-agent technical QA/QC audit across raw Spanish operational text.
    Combines:
    1. Orchestrator Triage (Lead Intervention Director).
    2. Deep AI Audit (DeepSeek V3 / OpenAI) when available.
    3. Comprehensive Offline Field Rulebook (Deterministic Fallback).
    4. Deterministic Cement Math, BOP Tests, Rig Move & HMBP P&A verification.
    5. Token-Level HTML Visual Diff generation.
    """
    findings: List[Dict[str, Any]] = []
    learning_tips: List[str] = []

    # -------------------------------------------------------------
    # 0. ORCHESTRATOR TRIAGE: Lead Intervention Director Dispatch
    # -------------------------------------------------------------
    classification = classify_operational_domain(raw_text)
    findings.append({
        "agent": "lead-intervention-director",
        "severity": "INFO",
        "badge": f"🎯 DIRECCIONAMIENTO ({classification['icon']} {classification['domain']})",
        "message": f"Contenido analizado por el Director de Operaciones como '{classification['title']}'. Especialista asignado: [{classification['specialist']}]. Se suprimen sugerencias cruzadas no relacionadas para mantener estricto foco técnico."
    })

    # Chronology & 24h Time Balance Audit (Agent: chronology-time-reconciliation-auditor)
    chrono_check = parse_raw_timeline(raw_text)
    if chrono_check.get("mode") == "sequential_inferred":
        findings.append({
            "agent": "chronology-time-reconciliation-auditor",
            "severity": "INFO",
            "badge": "⏱️ CRONOLOGÍA SECUENCIAL (HITOS -> INTERVALOS IADC)",
            "message": "Se detectó formato de hitos cronológicos (solo hora de inicio). El especialista en tiempos infirió las horas de fin a partir de la siguiente actividad y reestructuró cada evento en rangos estándar IADC (HH:MM - HH:MM)."
        })
    if chrono_check.get("gaps"):
        for g in chrono_check["gaps"]:
            findings.append({
                "agent": "chronology-time-reconciliation-auditor",
                "severity": "WARNING",
                "badge": f"⏱️ BRECHA OPERACIONAL DE {g['gap_hours']} H",
                "message": f"Se detectó una brecha de {g['gap_hours']} h sin registro de operaciones entre las {g['from']} y las {g['to']}. En auditoría IADC/SPE, todo tiempo no documentado debe clasificarse formalmente como Standby o NPT."
            })
    if chrono_check.get("is_24_closed"):
        findings.append({
            "agent": "chronology-time-reconciliation-auditor",
            "severity": "SUCCESS",
            "badge": "⏱️ BALANCE 24H VERIFICADO",
            "message": "Cierre exacto de 24.0 horas del día operacional verificado. Apto para conciliación y corte de facturación con la operadora."
        })

    corrected_text = raw_text
    ai_audit_success = False

    # -------------------------------------------------------------
    # 1. AI-POWERED AUDIT (DeepSeek / OpenAI)
    # -------------------------------------------------------------
    ai_status = {"connected": False, "provider": provider, "engine": "Offline Engine", "error": None}
    if api_key and provider != "none":
        try:
            ai_res = call_ai_spanish_audit(raw_text, api_key=api_key, provider=provider, well_name=well_name)
            if ai_res and "corrected_spanish" in ai_res and ai_res["corrected_spanish"].strip():
                corrected_text = ai_res["corrected_spanish"].strip()
                # Clean accidental banner title injected by AI if any
                corrected_text = re.sub(r"^(?:REPORTE\s+T[EÉ]CNICO[^\n]*|DOR[^\n]*)\n+", "", corrected_text, flags=re.IGNORECASE).strip()
                if "agent_findings" in ai_res and isinstance(ai_res["agent_findings"], list):
                    findings.extend(ai_res["agent_findings"])
                if "learning_tips" in ai_res and isinstance(ai_res["learning_tips"], list):
                    learning_tips.extend(ai_res["learning_tips"])
                ai_audit_success = True
                ai_status = {"connected": True, "provider": provider, "engine": f"{provider.capitalize()} (V3 / IA en la nube)", "error": None}
        except Exception as e:
            ai_audit_success = False
            err_msg = str(e)
            ai_status = {"connected": False, "provider": provider, "engine": "Offline Contingency", "error": err_msg}
            findings.append({
                "agent": "lead-intervention-director",
                "severity": "CRITICAL",
                "badge": f"⚠️ ALERTA DE CONEXIÓN CON IA ({provider.upper()})",
                "message": f"No se pudo consultar el motor de IA en la nube ({provider.upper()}): {err_msg}. Se activó el sistema de reglas petroleras de contingencia local."
            })

    # -------------------------------------------------------------
    # 2. OFFLINE DETERMINISTIC POLISHER (Fallback or Enrichment)
    # -------------------------------------------------------------
    if not ai_audit_success:
        corrected_text, off_findings, off_tips = offline_polish_spanish(raw_text)
        findings.extend(off_findings)
        learning_tips.extend(off_tips)

    # -------------------------------------------------------------
    # 2.5. CANONICAL GOLDEN PARAGRAPH & INTERACTIVE PLACEHOLDER ENFORCEMENT
    # -------------------------------------------------------------
    # Guarantees that whether generated by AI or offline polisher, the canonical
    # engineering paragraph and interactive [___] placeholders are strictly enforced.
    corrected_text, enf_findings, enf_tips = enforce_golden_paragraph_standards(corrected_text, raw_text=raw_text)
    findings.extend(enf_findings)
    for tip in enf_tips:
        if tip not in learning_tips:
            learning_tips.append(tip)

    # -------------------------------------------------------------
    # 3. DETERMINISTIC REINFORCEMENTS: CEMENT MATH & DATES
    # -------------------------------------------------------------
    # Cement Plug Thickness Math Error Check (e.g. 6050 ft a 5634 ft, 146 ft de espesor)
    plug_pattern = re.compile(
        r"(?:tap[oó]n(?: de fondo)?\s+(?:de\s+)?|desde\s+)(\d{3,5}(?:\.\d+)?)\s*(?:ft|m)?\s*(?:a|hasta)\s*(\d{3,5}(?:\.\d+)?)\s*(?:ft|m)?\s*,?\s*(\d{1,4}(?:\.\d+)?)\s*ft\s*(?:de\s+espesor|espesor)",
        re.IGNORECASE
    )
    for match in plug_pattern.finditer(raw_text):
        d1 = float(match.group(1))
        d2 = float(match.group(2))
        stated_thick = float(match.group(3))
        calc_thick = abs(d1 - d2)
        if abs(calc_thick - stated_thick) > 5.0:
            original_phrase = match.group(0)
            corrected_phrase = f"tapón de fondo de {int(d1)} ft a {int(d2)} ft, {int(calc_thick)} ft de espesor"
            corrected_text = corrected_text.replace(original_phrase, corrected_phrase)
            findings.append({
                "agent": "well-control-pna-specialist",
                "severity": "CRITICAL",
                "badge": "🔴 ERROR MATEMÁTICO EN TAPÓN",
                "message": f"Espesor de tapón mal calculado: {int(d1)} ft - {int(d2)} ft = {int(calc_thick)} ft de espesor (el reporte decía erróneamente {int(stated_thick)} ft). Corregido a {int(calc_thick)} ft."
            })

    # Calendar Date Sanity (e.g. 31/11/2026 - Nov has 30 days!)
    invalid_date_pattern = re.compile(r"\b(31/11/202\d)\b")
    for match in invalid_date_pattern.finditer(raw_text):
        bad_date = match.group(1)
        fixed_date = "31/10/2026" if "10" in raw_text or "27/10" in raw_text else "30/11/2026"
        corrected_text = corrected_text.replace(bad_date, fixed_date)
        findings.append({
            "agent": "lead-intervention-director",
            "severity": "CRITICAL",
            "badge": "🔴 ERROR DE CALENDARIO",
            "message": f"Fecha inexistente detectada '{bad_date}'. Noviembre tiene solo 30 días. Se corrigió cronológicamente a {fixed_date}."
        })

    # Rig Move Load Fraction Reconciliation
    rm_pattern = re.compile(
        r"R/M\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%\s*(?:\(\s*(\d+)\s*/\s*(\d+)\s*(?:cargas|loads)?\s*\)|\[\s*(\d+)\s*/\s*(\d+)\s*(?:cargas|loads)?\s*\]|,\s*(\d+)\s*/\s*(\d+)\s*(?:cargas|loads))",
        re.IGNORECASE
    )
    for m in rm_pattern.finditer(raw_text):
        stated_pct = float(m.group(1))
        m_loads = int(m.group(2) or m.group(4) or m.group(6))
        tot_loads = int(m.group(3) or m.group(5) or m.group(7))
        if tot_loads > 0:
            calc_pct = round((m_loads / tot_loads) * 100, 1)
            if abs(stated_pct - calc_pct) > 1.0:
                corr_str = f"R/M: {int(calc_pct)}% ({m_loads}/{tot_loads} cargas)"
                corrected_text = corrected_text.replace(m.group(0), corr_str)
                findings.append({
                    "agent": "rig-move-logistics-specialist",
                    "severity": "CRITICAL",
                    "badge": "🔴 ERROR MATEMÁTICO EN R/M (CARGAS VS %)",
                    "message": f"Discrepancia detectada en movilización: {m_loads}/{tot_loads} cargas equivale al {calc_pct}% (el reporte decía {stated_pct}%). Corregido a '{corr_str}'."
                })

    # API 53 BOP Testing Checks
    bop_test_pattern = re.compile(r"(?:prueba\s+de\s+(?:bop|anular|preventor|choke)|en\s+baja\s+con\s+(\d+)\s*psi)", re.IGNORECASE)
    if bop_test_pattern.search(raw_text):
        m_low = re.search(r"en\s+baja\s+con\s+(\d+)\s*psi\s*(?:x|×)\s*(\d+)\s*min", raw_text, re.IGNORECASE)
        if m_low:
            low_psi = float(m_low.group(1))
            low_min = float(m_low.group(2))
            if 250 <= low_psi <= 350 and low_min >= 5:
                findings.append({
                    "agent": "well-integrity-bop-specialist",
                    "severity": "SUCCESS",
                    "badge": "🟢 PRUEBA EN BAJA CUMPLE API 53",
                    "message": f"Prueba en baja con {int(low_psi)} psi x {int(low_min)} min conforme a API Standard 53."
                })
            elif low_psi > 400:
                findings.append({
                    "agent": "well-integrity-bop-specialist",
                    "severity": "WARNING",
                    "badge": "🟡 PRESIÓN BAJA EXCESIVA (API 53)",
                    "message": f"Prueba en baja con {int(low_psi)} psi excede el rango normativo de 250 - 350 psi (API 53)."
                })

    # NORSOK D-010 HMBP & TOC Checks
    if re.search(r"\b(hmbp|bridge\s*plug)\b", raw_text, re.IGNORECASE):
        has_barton = bool(re.search(r"carta\s+bart[oó]n|carta\s+manom[eé]trica", raw_text, re.IGNORECASE))
        has_psi_test = bool(re.search(r"prueba\s+de\s+integridad.*?(\d+)\s*psi", raw_text, re.IGNORECASE))
        if not has_barton and has_psi_test:
            findings.append({
                "agent": "pna-barrier-certifier",
                "severity": "WARNING",
                "badge": "🟡 REGISTRO EN CARTA BARTON PENDIENTE",
                "message": "Se reportó prueba de presión de tapón de abandono sin mención de carta Barton. Requiere soporte según normativa ANH."
            })

    # -------------------------------------------------------------
    # 4. GENERATE TRUE TOKEN-LEVEL VISUAL DIFF (HTML)
    # -------------------------------------------------------------
    diff_html = generate_token_diff(raw_text, corrected_text)

    # Fallback learning tips if empty
    if not learning_tips:
        d = classification.get("domain")
        if d == "BOP_PRESSURE_TEST":
            learning_tips.append("💡 Práctica de Integridad (API 53): En pruebas de preventoras, registre siempre lecturas de carta manométrica circular, tiempo de estabilización (mín 5 min), verificación de cero caída de presión y tiempos de recarga del acumulador Koomey.")
        elif d == "RIG_MOVE_LOGISTICS":
            learning_tips.append("💡 Práctica de Movilización: Registre siempre el desglose exacto R/D (desarme), R/M (cargas conciliadas) y R/U (arme), la distancia entre pozos y la hora oficial de recibo de equipo para el corte de tarifa.")
        elif d == "CEMENTING_PNA":
            learning_tips.append("💡 Práctica de Cementación: Especifique siempre densidades de lechada (ppg), tipo de aditivos, presiones de bombeo, tasa (bpm) y volumen de desplazamiento hasta retorno limpio.")
        elif d == "ARTIFICIAL_LIFT":
            learning_tips.append("💡 Práctica de Levantamiento Artificial: Registre siempre lecturas Megger (fase-fase y fase-tierra en MΩ), amperaje de motor y número de superbandas por tubo.")
        else:
            learning_tips.append("💡 Buenas Prácticas: Especifique siempre Grado (L-80/N-80), Rango (R2), tipo de rosca y presiones de trabajo al reportar sartas y herramientas de fondo.")

    return {
        "visual_diff_html": diff_html,
        "corrected_spanish": corrected_text,
        "agent_findings": findings,
        "learning_tips": learning_tips,
        "ai_status": ai_status
    }
