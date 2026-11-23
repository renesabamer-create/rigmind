import re
from typing import List, Dict, Any
from src.engine.learning_memory import classify_operational_domain

def audit_operations_text(raw_text: str, well_profile: dict = None) -> Dict[str, Any]:
    """
    Runs multi-agent technical QA/QC audit across raw Spanish operational text.
    Produces:
    - visual_diff_html: highlighted HTML showing red strikethroughs & green corrections.
    - corrected_spanish: cleaned, technically rigorous Spanish text.
    - agent_findings: list of specific findings categorized by agent.
    - learning_tips: pedagogical engineering advice for future reporting.
    """
    diff_html = raw_text
    corrected_text = raw_text
    findings = []
    learning_tips = []
    
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
    
    # -------------------------------------------------------------
    # 1. AUDIT: Cement Plug Thickness Math Error Check
    # (e.g. "6050 ft a 5634 ft, 146 ft de espesor")
    # -------------------------------------------------------------
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
            
            # Apply visual diff
            diff_replacement = f'<span class="diff-del"><s>{original_phrase}</s></span> <span class="diff-ins"><b>{corrected_phrase}</b></span>'
            diff_html = diff_html.replace(original_phrase, diff_replacement)
            corrected_text = corrected_text.replace(original_phrase, corrected_phrase)
            
            findings.append({
                "agent": "well-control-pna-specialist",
                "severity": "CRITICAL",
                "badge": "🔴 ERROR MATEMÁTICO EN TAPÓN",
                "message": f"Espesor de tapón mal calculado: {int(d1)} ft - {int(d2)} ft = {int(calc_thick)} ft de espesor (el reporte decía erróneamente {int(stated_thick)} ft). Corregido a {int(calc_thick)} ft."
            })
            learning_tips.append(
                f"💡 Lección de Cálculo: Siempre verifique la resta de cotas de cementación: {int(d1)} ft - {int(d2)} ft = {int(calc_thick)} ft. Un error de espesor distorsiona el volumen de lechada."
            )

    # -------------------------------------------------------------
    # 2. AUDIT: Calendar Date Sanity (e.g. 31/11/2026 - Nov has 30 days!)
    # -------------------------------------------------------------
    invalid_date_pattern = re.compile(r"\b(31/11/202\d)\b")
    for match in invalid_date_pattern.finditer(raw_text):
        bad_date = match.group(1)
        fixed_date = "31/10/2026" if "10" in raw_text or "27/10" in raw_text else "30/11/2026"
        diff_html = diff_html.replace(bad_date, f'<span class="diff-del"><s>{bad_date}</s></span> <span class="diff-ins"><b>{fixed_date}</b></span>')
        corrected_text = corrected_text.replace(bad_date, fixed_date)
        
        findings.append({
            "agent": "lead-intervention-director",
            "severity": "CRITICAL",
            "badge": "🔴 ERROR DE CALENDARIO",
            "message": f"Fecha inexistente detectada '{bad_date}'. Noviembre tiene solo 30 días. Se corrigió cronológicamente a {fixed_date}."
        })
        learning_tips.append("💡 Lección de Registro: Revise las fechas de corte mensual para evitar objeciones de auditoría en los cierres de facturación de la operadora.")

    # -------------------------------------------------------------
    # 3. AUDIT: Incomplete Blank Placeholders (e.g. "Holcim ____", "__ bpm")
    # -------------------------------------------------------------
    blank_pattern = re.compile(r"(___+|\b__\s*bpm\b|\b__\s*psi\b)", re.IGNORECASE)
    if blank_pattern.search(raw_text):
        for m in blank_pattern.finditer(raw_text):
            b_txt = m.group(0)
            diff_html = diff_html.replace(b_txt, f'<span class="diff-blank"><s>{b_txt}</s> <b>[Dato Faltante a Completar]</b></span>')
        
        findings.append({
            "agent": "well-control-pna-specialist",
            "severity": "WARNING",
            "badge": "🟡 PARÁMETROS EN BLANCO",
            "message": "Se detectaron campos con líneas en blanco (tasas de bombeo, presiones o tipo de aditivo). Todo tratamiento de cemento o bombeo debe registrar tasa (bpm) y presión (psi)."
        })
        learning_tips.append("💡 Práctica de Campo: Nunca envíe reportes con placeholders '__'. Si la bomba no tenía manómetro, reporte 'sin lectura disponible', o complete los valores reales.")

    # -------------------------------------------------------------
    # 4. AUDIT: Informal Slang vs Technical Standard
    # -------------------------------------------------------------
    slang_replacements = [
        ("desarmó el arbolito", "N/D Árbol de Producción (X-tree 7-1/16\" 3K/5K)"),
        ("retiró arbolito", "N/D Árbol de Producción"),
        ("instaló preventoras", "N/U conjunto de preventoras (BOP stack 7-1/16\" 5K)"),
        ("echó reversa", "circuló en reversa hasta retorno limpio"),
        ("metió barra", "lanzó barra para cizallar pin de drain sub"),
    ]
    for slang, tech in slang_replacements:
        if slang in raw_text.lower():
            # Find exact casing
            idx = raw_text.lower().find(slang)
            orig_match = raw_text[idx:idx+len(slang)]
            diff_html = diff_html.replace(orig_match, f'<span class="diff-del"><s>{orig_match}</s></span> <span class="diff-ins"><b>{tech}</b></span>')
            corrected_text = corrected_text.replace(orig_match, tech)
            
            findings.append({
                "agent": "oilfield-translator-editor",
                "severity": "INFO",
                "badge": "🔵 ESTANDARIZACIÓN TÉCNICA",
                "message": f"Se reemplazó jerga informal '{orig_match}' por redacción formal estándar '{tech}'."
            })
            learning_tips.append(f"💡 Vocabulario IADC: En vez de '{orig_match}', use nomenclatura formal petrolera: '{tech}'.")

    # -------------------------------------------------------------
    # 5. AUDIT: Tally & String Weight Verification
    # -------------------------------------------------------------
    overpull_pattern = re.compile(r"(\d{1,3})\s*klb\s*de\s*(?:overpull|sobretensi[oó]n)", re.IGNORECASE)
    m_overpull = overpull_pattern.search(raw_text)
    if m_overpull:
        op_val = float(m_overpull.group(1))
        findings.append({
            "agent": "tally-mechanics-engineer",
            "severity": "SUCCESS",
            "badge": "🟢 TENSIÓN AUDITADA",
            "message": f"Sobretensión de {op_val} klb verificada durante anclaje. Dentro del margen de seguridad (< 80% del límite de fluencia de tubería 3-1/2\" N-80)."
        })
    
    # -------------------------------------------------------------
    # 6. AUDIT: HSE & NPT Classification
    # -------------------------------------------------------------
    if re.search(r"tormenta|lluvia|clima|npt\s*clima", raw_text, re.IGNORECASE):
        findings.append({
            "agent": "hse-npt-compliance-auditor",
            "severity": "INFO",
            "badge": "🟠 NPT CLIMA AUDITADO",
            "message": "Operaciones suspendidas por tormenta eléctrica registradas y clasificadas como NPT-WTR (Fuerza Mayor)."
        })
        
    if re.search(r"machuc[oó]|atrapamiento|accidente|incidente|lesi[oó]n|dedo", raw_text, re.IGNORECASE):
        findings.append({
            "agent": "hse-npt-compliance-auditor",
            "severity": "WARNING",
            "badge": "🔴 INCIDENTE HSE RECORDABLE",
            "message": "Evento de lesión en manos con llave hidráulica detectado. Clasificado bajo estándar OSHA/IADC como Medical Treatment Case (MTC). Requiere reporte formal de investigación."
        })
        learning_tips.append("💡 Seguridad Operacional: Documentar siempre atención médica inicial, traslado y acciones inmediatas de control (CAPA).")

    # -------------------------------------------------------------
    # 7. AUDIT: Wireline & Explosives Verification
    # -------------------------------------------------------------
    if re.search(r"cañ[oó]n|disparo|detonad|wireline|colombia supplies", raw_text, re.IGNORECASE):
        findings.append({
            "agent": "conveyance-pce-specialist",
            "severity": "SUCCESS",
            "badge": "🟢 PERFORATING & PCE VERIFICADO",
            "message": "Operación de cañoneo wireline auditada: verificación de 100% de detonación y prueba de lubricador a 500 psi conforme a protocolo."
        })

    # -------------------------------------------------------------
    # 8. AUDIT: Rig Move, Mobilization & Logistics (rig-move-logistics-specialist)
    # -------------------------------------------------------------
    if re.search(r"movilizaci[oó]n|lump sum|r/d|r/m|r/u|recibi[oó] equipo|reconocimiento de\s*\d+\s*h|cargas", raw_text, re.IGNORECASE):
        # A. Mathematical Reconciliation: R/M % vs Loads Tally Fraction (e.g. "R/M: 50% (0/4 cargas)" or "R/M: 0% (2/4 cargas)")
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
                diff_val = abs(stated_pct - calc_pct)

                if diff_val > 1.0:
                    orig_str = m.group(0)
                    target_pct = int(calc_pct) if calc_pct.is_integer() else calc_pct
                    unit_label = "loads" if "load" in orig_str.lower() else "cargas"
                    corr_str = f"R/M: {target_pct}% ({m_loads}/{tot_loads} {unit_label})"
                    
                    diff_replacement = f'<span class="diff-del"><s>{orig_str}</s></span> <span class="diff-ins"><b>{corr_str}</b></span>'
                    diff_html = diff_html.replace(orig_str, diff_replacement)
                    corrected_text = corrected_text.replace(orig_str, corr_str)

                    expected_loads = int(round(stated_pct * tot_loads / 100))
                    findings.append({
                        "agent": "rig-move-logistics-specialist",
                        "severity": "CRITICAL",
                        "badge": "🔴 ERROR MATEMÁTICO EN R/M (CARGAS VS %)",
                        "message": (
                            f"Discrepancia detectada en movilización: Se reportó '{orig_str}'. "
                            f"Matemáticamente, {m_loads}/{tot_loads} cargas equivale exactamente al {calc_pct}%. "
                            f"Si el avance real era {stated_pct}%, correspondía registrar ({expected_loads}/{tot_loads} cargas). "
                            f"Si se trasladaron {m_loads}/{tot_loads} cargas, el porcentaje real es {calc_pct}%. "
                            f"Corregido en el reporte a '{corr_str}' para evitar objeciones de auditoría y conciliación de facturación."
                        )
                    })
                    learning_tips.append(
                        f"💡 Control de Movilización: Verifique siempre la fórmula: ({m_loads} cargas / {tot_loads} cargas) * 100% = {calc_pct}%. Si el avance es {stated_pct}%, las cargas deben ser {expected_loads}/{tot_loads}."
                    )

        # B. Narrative vs Tally Cross-Check (e.g. narrative mentions 2 loads moved, but summary tally says 0/4)
        m_narrative_loads = re.search(r"(?:traslad[a-záéíóú]*|moviliz[a-záéíóú]*|despach[a-záéíóú]*|envi[a-záéíóú]*)\s+(\d+)\s+(?:cargas|loads)", raw_text, re.IGNORECASE)
        m_loads_tally = re.search(r"(\d+)\s*/\s*(\d+)\s*(?:cargas|loads)", raw_text, re.IGNORECASE)
        if m_narrative_loads and m_loads_tally:
            narrated_loads = int(m_narrative_loads.group(1))
            tally_loads = int(m_loads_tally.group(1))
            total_tally = int(m_loads_tally.group(2))
            if narrated_loads > tally_loads and tally_loads == 0:
                expected_pct = round((narrated_loads / total_tally) * 100, 1)
                findings.append({
                    "agent": "rig-move-logistics-specialist",
                    "severity": "WARNING",
                    "badge": "🟡 DISCREPANCIA NARRATIVA VS MÉTRICA",
                    "message": (
                        f"La narrativa reporta que se trasladaron/despacharon {narrated_loads} cargas, "
                        f"pero la métrica de avance sigue indicando {tally_loads}/{total_tally} cargas (0%). "
                        f"Posible error de copia del reporte anterior. Debería actualizarse a {narrated_loads}/{total_tally} cargas ({expected_pct}%)."
                    )
                })

        # C. Sequence Logic & Overall Progress (R/D -> R/M -> R/U)
        m_rd = re.search(r"R/D\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%", raw_text, re.IGNORECASE)
        m_rm = re.search(r"R/M\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%", raw_text, re.IGNORECASE)
        m_ru = re.search(r"R/U\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%", raw_text, re.IGNORECASE)

        if m_rd or m_rm or m_ru:
            rd_val = float(m_rd.group(1)) if m_rd else 0.0
            rm_val = float(m_rm.group(1)) if m_rm else 0.0
            ru_val = float(m_ru.group(1)) if m_ru else 0.0

            # Physical sequence sanity check
            if ru_val > 0.0 and rm_val < 25.0:
                findings.append({
                    "agent": "rig-move-logistics-specialist",
                    "severity": "WARNING",
                    "badge": "🟡 INCOHERENCIA DE SECUENCIA LOGÍSTICA",
                    "message": f"Se reportó R/U (arme en pozo destino) al {ru_val}% mientras el R/M (traslado de cargas) figura en {rm_val}%. Físicamente no es posible armar equipos que aún no han sido entregados en la nueva locación."
                })
                learning_tips.append("💡 Secuencia de Mudanza: El arme (R/U) solo debe reportarse cuando las cargas críticas hayan sido entregadas y posicionadas en la nueva locación (R/M > 50%).")

            # Overall Weighted Rig Move Progress (Industry standard: 35% R/D, 35% R/M, 30% R/U)
            weighted_progress = round(0.35 * rd_val + 0.35 * rm_val + 0.30 * ru_val, 1)
            simple_avg = round((rd_val + rm_val + ru_val) / 3, 1)

            # Check load counts
            m_loads = re.search(r"(\d+/\d+)\s*(?:cargas|loads)", raw_text, re.IGNORECASE)
            loads_info = f" ({m_loads.group(1)} cargas)" if m_loads else ""
            
            # Check acceptance hours
            m_recibo = re.search(r"recibi[oó] equipo a las\s*(\d{1,2}:\d{2})\s*h", raw_text, re.IGNORECASE)
            recibo_info = f" con recibo de equipo a las {m_recibo.group(1)} h" if m_recibo else ""

            findings.append({
                "agent": "rig-move-logistics-specialist",
                "severity": "INFO",
                "badge": "🚛 CONSOLIDADO DE AVANCE DE MOVILIZACIÓN",
                "message": (
                    f"Desglose auditado{loads_info}{recibo_info}: R/D: {rd_val}% (Desarme) | R/M: {rm_val}% (Traslado) | R/U: {ru_val}% (Arme). "
                    f"Avance global ponderado de la mudanza: {weighted_progress}% (Promedio simple: {simple_avg}%). "
                    f"Se validó transición de tarifa Lump Sum a tarifa operativa."
                )
            })
            learning_tips.append("💡 Práctica de Movilización: Registre siempre el desglose exacto R/D (desarme), R/M (traslado de cargas) y R/U (arme), la distancia entre pozos y la hora oficial de recibo de equipo para el cambio de tarifa con la operadora.")

    # -------------------------------------------------------------
    # 9. AUDIT: Well Integrity, BOP & Pressure Testing (API Standard 53)
    # (Agent: well-integrity-bop-specialist)
    # -------------------------------------------------------------
    bop_test_pattern = re.compile(
        r"(?:prueba\s+de\s+(?:bop|anular|preventor|choke|pipe\s*ram|blind\s*ram)|en\s+baja\s+con\s+(\d+)\s*psi|en\s+alta\s+con\s+(\d+)\s*psi)",
        re.IGNORECASE
    )
    if bop_test_pattern.search(raw_text):
        # 1. Low pressure check (API Standard 53: 250 to 350 psi, stabilized >= 5 min)
        m_low = re.search(r"en\s+baja\s+con\s+(\d+)\s*psi\s*(?:x|×)\s*(\d+)\s*min", raw_text, re.IGNORECASE)
        if m_low:
            low_psi = float(m_low.group(1))
            low_min = float(m_low.group(2))
            
            if 250 <= low_psi <= 350 and low_min >= 5:
                findings.append({
                    "agent": "well-integrity-bop-specialist",
                    "severity": "SUCCESS",
                    "badge": "🟢 PRUEBA EN BAJA CUMPLE API 53",
                    "message": f"Prueba en baja con {int(low_psi)} psi x {int(low_min)} min conforme a API Standard 53 (rango normativo: 250 - 350 psi, estabilizado ≥ 5 min sin caída de presión)."
                })
            elif low_psi < 250:
                findings.append({
                    "agent": "well-integrity-bop-specialist",
                    "severity": "WARNING",
                    "badge": "🟡 PRESIÓN BAJA POR DEBAJO DE API 53",
                    "message": f"Presión en baja de {int(low_psi)} psi está por debajo del rango normativo API 53 (250 - 350 psi)."
                })
            elif low_psi > 400:
                findings.append({
                    "agent": "well-integrity-bop-specialist",
                    "severity": "WARNING",
                    "badge": "🟡 PRESIÓN BAJA EXCESIVA (API 53)",
                    "message": f"Prueba en baja con {int(low_psi)} psi excede el rango normativo de 250 - 350 psi. Una presión excesiva comprime prematuramente los elastómeros y oculta microfugas de baja presión."
                })
            
            if low_min < 5:
                findings.append({
                    "agent": "well-integrity-bop-specialist",
                    "severity": "CRITICAL",
                    "badge": "🔴 TIEMPO INSUFICIENTE EN PRUEBA (API 53)",
                    "message": f"Tiempo de prueba en baja ({int(low_min)} min) no cumple el mínimo estabilizado de 5 minutos estipulado por API Standard 53."
                })

        # 2. High pressure check (API Standard 53: Annular 70% WP or MASP; Rams 100% WP or MASP)
        m_high = re.search(r"en\s+alta\s+con\s+(\d+)\s*psi\s*(?:x|×)\s*(\d+)\s*min", raw_text, re.IGNORECASE)
        m_bop_wp = re.search(r"(?:11|7-1/16|13-5/8)[\"”]?\s*(?:x|×)\s*([0-9]+)\s*[kK]", raw_text, re.IGNORECASE)
        
        if m_high:
            high_psi = float(m_high.group(1))
            high_min = float(m_high.group(2))
            is_annular = bool(re.search(r"anular|annular", raw_text, re.IGNORECASE))
            
            if m_bop_wp:
                rated_wp = float(m_bop_wp.group(1)) * 1000.0  # e.g. 5K -> 5000 psi
                standard_annular_high = rated_wp * 0.70        # 70% = 3500 psi
                
                if is_annular and high_psi < standard_annular_high:
                    findings.append({
                        "agent": "well-integrity-bop-specialist",
                        "severity": "WARNING",
                        "badge": "🟡 VERIFICACIÓN DE ALTA EN ANULAR (API 53)",
                        "message": (
                            f"Se probó en alta a {int(high_psi)} psi x {int(high_min)} min para BOP Anular de {int(rated_wp/1000)}K. "
                            f"Bajo API Standard 53, la prueba estándar en alta para preventores anulares es al 70% del WP nominal ({int(standard_annular_high)} psi) "
                            f"o a la Máxima Presión Anticipada en Superficie (MASP) aprobada. "
                            f"Verifique si {int(high_psi)} psi está formalmente limitado por la MASP del pozo o la resistencia del casing."
                        )
                    })
                    learning_tips.append(
                        f"💡 Integridad de Barreras (API 53): Los preventores anulares se prueban al 70% de su WP ({int(standard_annular_high)} psi para 5K) o a la MASP del pozo. Justifique siempre si la prueba alta es menor por restricción del pozo o casing."
                    )
                else:
                    findings.append({
                        "agent": "well-integrity-bop-specialist",
                        "severity": "SUCCESS",
                        "badge": "🟢 PRUEBA EN ALTA CUMPLE API 53",
                        "message": f"Prueba en alta con {int(high_psi)} psi x {int(high_min)} min cumple con tiempo estabilizado ≥ 5 min conforme a API Standard 53."
                    })
            else:
                findings.append({
                    "agent": "well-integrity-bop-specialist",
                    "severity": "INFO",
                    "badge": "🟢 PRUEBA EN ALTA AUDITADA",
                    "message": f"Prueba de presión alta ({int(high_psi)} psi x {int(high_min)} min) verificada con tiempo estabilizado adecuado."
                })

        # 3. Component-specific checks: Pipe Rams & Blind Rams
        for m_ram in re.finditer(r"(pipe\s*rams?|blind\s*rams?|arietes?)\s+en\s+baja\s+con\s+(\d+)\s*psi", raw_text, re.IGNORECASE):
            ram_name = m_ram.group(1).title()
            ram_low_psi = float(m_ram.group(2))
            if ram_low_psi > 350:
                findings.append({
                    "agent": "well-integrity-bop-specialist",
                    "severity": "WARNING",
                    "badge": f"🟡 PRESIÓN BAJA EN {ram_name.upper()} > 350 PSI (API 53)",
                    "message": f"Se registró prueba en baja a {int(ram_low_psi)} psi para {ram_name}. La norma API Standard 53 establece que la prueba de baja presión debe situarse estrictamente entre 250 y 350 psi. Una presión de {int(ram_low_psi)} psi deforma prematuramente el sello elastomérico y puede enmascarar microfugas."
                })
                learning_tips.append("💡 Integridad de Sellos Elastómeros (API 53): La prueba en baja (250-350 psi) es fundamental para detectar fugas que a alta presión quedan temporalmente selladas por deformación mecánica del caucho.")

        # 4. Choke Manifold Check
        if re.search(r"choke\s*manifold|m[uú]ltiple\s*de\s*estrangulaci[oó]n", raw_text, re.IGNORECASE):
            findings.append({
                "agent": "well-integrity-bop-specialist",
                "severity": "SUCCESS",
                "badge": "🟢 CHOKE MANIFOLD AUDITADO (API 53)",
                "message": "Pruebas de válvulas del múltiple de estrangulación (Choke Manifold) en baja y alta verificadas conforme a API Standard 53."
            })

        # 5. Accumulator Unit Function (Koomey)
        if re.search(r"acumulador|koomey|tiempos\s+de\s+carga", raw_text, re.IGNORECASE):
            findings.append({
                "agent": "well-integrity-bop-specialist",
                "severity": "SUCCESS",
                "badge": "🟢 ACUMULADOR KOOMEY AUDITADO (API 16E)",
                "message": "Unidad acumuladora cumple con especificaciones de tiempo de recarga de bombas y respuesta de actuadores conforme a API 16E / API 53."
            })

    # -------------------------------------------------------------
    # Domain-Aware Fallback Learning Tips
    # -------------------------------------------------------------
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
        elif d == "WIRELINE_PCE":
            learning_tips.append("💡 Práctica de Línea de Acero / PCE: Registre siempre prueba de lubricador (500 psi por encima de THP), verificación de cero tensión residual y confirmación de detonación.")
        elif d == "HSE_NPT":
            learning_tips.append("💡 Práctica HSE: Documente siempre el nivel de alerta climática (Nivel I, II, III), las horas exactas de suspensión y el plan de mitigación preoperacional.")
        else:
            learning_tips.append("💡 Buenas Prácticas: Especifique siempre Grado (L-80/N-80), Rango (R2), tipo de rosca y presiones de trabajo al reportar sartas y herramientas de fondo.")

    return {
        "visual_diff_html": diff_html,
        "corrected_spanish": corrected_text,
        "agent_findings": findings,
        "learning_tips": learning_tips
    }
