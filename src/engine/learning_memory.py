import json
import os
import re
from typing import List, Dict, Any, Tuple

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "learning_memory.json")

def load_memory() -> List[Dict[str, Any]]:
    """Loads saved golden examples from JSON."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_to_memory(exemplar: Dict[str, Any]) -> bool:
    """Appends a new user-approved golden example to the learning memory."""
    memory = load_memory()
    exemplar["id"] = f"gold-{len(memory) + 1:03d}"
    memory.append(exemplar)
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def classify_operational_domain(text: str) -> Dict[str, str]:
    """
    Classifies the operational domain of the text to route to the correct specialist
    and apply domain-appropriate maturity scoring and QA/QC rules.
    """
    t_lower = text.lower()
    
    # 1. P&A, Bridge Plugs & Mechanical Barriers (Highest Priority Downhole Isolation)
    if re.search(r'\b(hmbp|bridge\s*plug|tap[oó]n|cemento|lechada|woc|toc|boc|squeeze|abandono|p&a|fraguado|testigos?)\b', t_lower):
        return {
            "domain": "PNA_BARRIER_ISOLATION",
            "specialist": "pna-barrier-certifier",
            "title": "Aislamiento de Barreras, Tapones HMBP y Abandono Definitivo (NORSOK D-010 / API RP 96)",
            "icon": "🧱"
        }

    # 2. BOP & Well Integrity Pressure Testing
    if re.search(r'\b(bop|anular|pipe\s*rams?|blind\s*rams?|shear\s*rams?|choke\s*manifold|preventor(?:as?)?|acumulador|koomey)\b', t_lower):
        if re.search(r'\b(prueba|presi[oó]n|en\s+baja|en\s+alta|psi)\b', t_lower):
            return {
                "domain": "BOP_PRESSURE_TEST",
                "specialist": "well-integrity-bop-specialist",
                "title": "Prueba de Integridad de Preventoras (BOP) y Barreras (API 53)",
                "icon": "🛡️"
            }
            
    # 3. Rig Move & Logistics
    if re.search(r'\b(movilizaci[oó]n|mudanza|desarme|arme|r/d|r/m|r/u|cargas?|recibo\s+de\s+equipo|lump\s+sum)\b', t_lower):
        return {
            "domain": "RIG_MOVE_LOGISTICS",
            "specialist": "rig-move-logistics-specialist",
            "title": "Movilización, Logística y Arme/Desarme de Taladro",
            "icon": "🚛"
        }
        
    # 4. Artificial Lift (ESP/SRP/Gas Lift/PCP)
    if re.search(r'\b(esp|bes|electrosumergible|megger|motor|superbandas?|cable\s+de\s+potencia|balanc[ií]n|varillas?|sucker\s+rod|gas\s+lift|pcp)\b', t_lower):
        return {
            "domain": "ARTIFICIAL_LIFT",
            "specialist": "artificial-lift-systems-specialist",
            "title": "Sistemas de Levantamiento Artificial (ESP / SRP / Gas Lift / PCP)",
            "icon": "⚡"
        }
        
    # 5. Wireline & PCE
    if re.search(r'\b(wireline|slickline|cañ[oó]n|perforaci[oó]n|disparo|cbl|vdl|usit|plt|lubricador)\b', t_lower):
        return {
            "domain": "WIRELINE_PCE",
            "specialist": "conveyance-pce-specialist",
            "title": "Línea de Acero, Registros y Cañoneo (PCE / Wireline)",
            "icon": "🎯"
        }
        
    # 6. Tubulars & Tripping
    if re.search(r'\b(rih|pooh|m/u|l/d|tbg|csg|tuber[ií]a|sarta|bha|sencillos|paradas|quebrando)\b', t_lower):
        return {
            "domain": "TUBULARS_TRIPPING",
            "specialist": "tally-mechanics-engineer",
            "title": "Maniobra de Tubería, Tallies y Mecánica de Sarta",
            "icon": "⚙️"
        }
        
    # 7. HSE & NPT
    if re.search(r'\b(tormenta|lluvia|npt|charla|seguridad|accidente|incidente|lesi[oó]n)\b', t_lower):
        return {
            "domain": "HSE_NPT",
            "specialist": "hse-npt-compliance-auditor",
            "title": "Seguridad Operacional (HSE) y Tiempos No Productivos (NPT)",
            "icon": "⚠️"
        }
        
    return {
        "domain": "GENERAL_OPERATIONS",
        "specialist": "lead-intervention-director",
        "title": "Operaciones Generales de Intervención de Pozos",
        "icon": "📋"
    }


def calculate_maturity_score(text: str) -> Dict[str, Any]:
    """
    Evaluates the technical completeness and maturity level of an operations narrative
    specifically tailored to the operational domain classified by the Lead Intervention Director.
    Scored from 0% to 100%.
    """
    classification = classify_operational_domain(text)
    domain = classification["domain"]
    t_lower = text.lower()
    
    score = 15 # baseline
    checks = []
    missing_for_next_level = []
    
    # -----------------------------------------------------------------
    # DOMAIN 1: BOP & Well Integrity Pressure Testing (API Standard 53)
    # -----------------------------------------------------------------
    if domain == "BOP_PRESSURE_TEST":
        # 1. Low Pressure Test + Holding Time
        has_low = bool(re.search(r'en\s+baja\s+con\s+(\d+)\s*psi', t_lower))
        has_low_time = bool(re.search(r'en\s+baja\s+con\s+\d+\s*psi\s*(?:x|×)\s*(\d+)\s*min', t_lower))
        if has_low and has_low_time:
            score += 20
            checks.append("✅ Prueba de baja presión (250-350 psi) y tiempo de sostenimiento estabilizado (API 53)")
        elif has_low:
            score += 10
            missing_for_next_level.append("Tiempo estabilizado de prueba en baja (ej. 5 o 10 min)")
        else:
            missing_for_next_level.append("Presión de prueba en baja (rango API 53: 250 - 350 psi)")
            
        # 2. High Pressure Test + Holding Time
        has_high = bool(re.search(r'en\s+alta\s+con\s+(\d+)\s*psi', t_lower))
        has_high_time = bool(re.search(r'en\s+alta\s+con\s+\d+\s*psi\s*(?:x|×)\s*(\d+)\s*min', t_lower))
        if has_high and has_high_time:
            score += 20
            checks.append("✅ Prueba de alta presión y tiempo de sostenimiento estabilizado (API 53)")
        elif has_high:
            score += 10
            missing_for_next_level.append("Tiempo estabilizado de prueba en alta (ej. 10 min)")
        else:
            missing_for_next_level.append("Presión de prueba en alta (WP nominal o MASP)")
            
        # 3. BOP Stack Dimension & Working Pressure Rating
        has_specs = bool(re.search(r'\d(?:-\d/\d)?"\s*(?:x|×)\s*\d+[kK]', text))
        if has_specs:
            score += 15
            checks.append("✅ Diámetro de paso y presión nominal del conjunto BOP especificados (ej. 7-1/16\" 5K)")
        else:
            missing_for_next_level.append("Diámetro de paso y capacidad de trabajo del BOP (ej. 7-1/16\" 5K o 11\" 5K)")
            
        # 4. Multi-Component Stack Breadth (Annular, Pipe Rams, Blind/Shear)
        has_rams = bool(re.search(r'pipe\s*rams?|blind\s*rams?|shear\s*rams?|arietes?', t_lower))
        has_annular = bool(re.search(r'anular|annular', t_lower))
        if has_rams and has_annular:
            score += 15
            checks.append("✅ Evaluación integral de componentes: Preventor Anular + Arietes (Pipe & Blind Rams)")
        elif has_annular:
            score += 10
            missing_for_next_level.append("Pruebas de arietes de tubería y ciegos (Pipe Rams y Blind Rams)")
        else:
            missing_for_next_level.append("Prueba de preventor anular")
            
        # 5. Choke Manifold System
        has_choke = bool(re.search(r'choke\s*manifold|v[aá]lvulas?\s*(?:no\.?\s*\d+|\d+)', t_lower))
        if has_choke:
            score += 15
            checks.append("✅ Múltiple de estrangulación (Choke Manifold) auditado con desglose de válvulas")
        else:
            missing_for_next_level.append("Pruebas individuales de válvulas del Choke Manifold")
            
        # 6. Accumulator / Auxiliary Barrier Verification
        has_accum = bool(re.search(r'acumulador|koomey|tiempos\s+de\s+carga|botellas', t_lower))
        if has_accum:
            score += 15
            checks.append("✅ Verificación de unidad acumuladora Koomey y tiempos de recarga (API 16E)")
        else:
            missing_for_next_level.append("Verificación de tiempos de cierre y recarga del Acumulador Koomey")

    # -----------------------------------------------------------------
    # DOMAIN 2: Rig Move, Mobilization & Logistics
    # -----------------------------------------------------------------
    elif domain == "RIG_MOVE_LOGISTICS":
        has_rd = bool(re.search(r'r/d\s*[:=]?\s*\d+%', t_lower))
        has_rm = bool(re.search(r'r/m\s*[:=]?\s*\d+%', t_lower))
        has_ru = bool(re.search(r'r/u\s*[:=]?\s*\d+%', t_lower))
        has_loads = bool(re.search(r'\d+/\d+\s*cargas?', t_lower))
        has_wells = bool(re.search(r'desde\s+(?:el\s+)?pozo.*?hacia\s+(?:el\s+)?pozo', t_lower))
        has_recibo = bool(re.search(r'recibi[oó]\s+equipo|tarifa|lump\s+sum', t_lower))

        if has_rd and has_rm and has_ru:
            score += 25
            checks.append("✅ Desglose trifásico de avance registrado: R/D (Desarme), R/M (Traslado), R/U (Arme)")
        else:
            missing_for_next_level.append("Desglose porcentual exacto R/D, R/M y R/U")

        if has_loads:
            score += 20
            checks.append("✅ Censo y conciliación de cargas movilizadas especificado (M/N cargas)")
        else:
            missing_for_next_level.append("Conteo y balance de cargas movilizadas (ej. 2/4 cargas)")

        if has_wells:
            score += 15
            checks.append("✅ Trazabilidad geográfica: pozo origen y pozo destino identificados")
        else:
            missing_for_next_level.append("Identificación de pozo de origen y pozo de destino")

        if bool(re.search(r'\d+\s*m\b|mismo\s+pad|locaci[oó]n', t_lower)):
            score += 15
            checks.append("✅ Distancia entre pozos y contexto de pad documentados")
        else:
            missing_for_next_level.append("Distancia de traslado en metros o contexto de pad")

        if has_recibo:
            score += 15
            checks.append("✅ Hora oficial de recibo de equipo y condición contractual de tarifa")
        else:
            missing_for_next_level.append("Hora de recibo de equipo para corte de tarifa contractual")

    # -----------------------------------------------------------------
    # DOMAIN 3: Cementing & P&A
    # -----------------------------------------------------------------
    elif domain == "CEMENTING_PNA":
        has_depths = bool(re.search(r'\d{3,5}\s*ft.*?hasta.*?\d{3,5}\s*ft|\d{3,5}\s*ft\s*a\s*\d{3,5}\s*ft', t_lower))
        has_density = bool(re.search(r'\d+(?:\.\d+)?\s*ppg', t_lower))
        has_rates = bool(re.search(r'\d+(?:\.\d+)?\s*bpm|\d+\s*psi', t_lower))
        has_thick = bool(re.search(r'\d+\s*ft\s*(?:de\s+espesor|espesor)', t_lower))
        has_woc = bool(re.search(r'woc|fraguado|toc|testigos?', t_lower))

        if has_depths:
            score += 20
            checks.append("✅ Intervalo de profundidad (tope y base) claramente definido")
        else:
            missing_for_next_level.append("Cotas de profundidad del tapón (ej. 5720 ft a 5304 ft)")

        if has_thick:
            score += 15
            checks.append("✅ Espesor del tapón de cemento calculado y verificado")
        else:
            missing_for_next_level.append("Espesor del tapón verificado")

        if has_density:
            score += 20
            checks.append("✅ Densidad de lechada de cemento especificada en ppg")
        else:
            missing_for_next_level.append("Densidad de lechada en ppg (ej. 15.8 ppg Clase G)")

        if has_rates:
            score += 15
            checks.append("✅ Parámetros de bombeo: tasa (bpm) y presión (psi)")
        else:
            missing_for_next_level.append("Tasa de bombeo (bpm) y presión de inyección (psi)")

        if has_woc:
            score += 15
            checks.append("✅ Verificación de tiempo de fraguado (WOC) o confirmación de TOC")
        else:
            missing_for_next_level.append("Tiempo de fraguado (WOC) o verificación con peso del TOC")

    # -----------------------------------------------------------------
    # DOMAIN 4: Tubulars, Tripping & Mechanics (POOH / RIH / Tally)
    # -----------------------------------------------------------------
    elif domain == "TUBULARS_TRIPPING":
        # 1. Cotas de profundidad inicial y final
        has_depths = bool(re.search(r'desde\s+\d{2,5}\s*(?:ft|m).*?hasta\s+\d{2,5}\s*(?:ft|m)|\b\d{2,5}\s*(?:ft|m)\s*(?:a|-)\s*\d{2,5}\s*(?:ft|m)', t_lower))
        if has_depths:
            score += 15
            checks.append("✅ Cotas de maniobra verificadas: Profundidad inicial y final (ft)")
        else:
            missing_for_next_level.append("Cotas de profundidad inicial y final (ej. desde 5518 ft hasta 5456 ft)")

        # 2. Conteo de juntas (Tally) y Avance Porcentual Calculado
        has_tally = bool(re.search(r'\(?\s*\d+\s*/\s*\d+\s*(?:jtas?|juntas?|jts?)\s*\)?', t_lower))
        has_pct = bool(re.search(r'avance\s*[:=]?\s*\d+(?:\.\d+)?%', t_lower))
        if has_tally and has_pct:
            score += 15
            checks.append("✅ Tally de juntas y avance porcentual calculado matemáticamente (ej. 4/150 jtas, avance: 2.7%)")
        elif has_tally:
            score += 10
            missing_for_next_level.append("Avance porcentual calculado matemáticamente (ej. avance: 2.7%)")
        else:
            missing_for_next_level.append("Conteo de juntas fraccionario (ej. 4/150 jtas) y porcentaje de avance")

        # 3. Especificación completa del tubular (Tipo, OD, lb/ft, Grado, Rosca)
        has_pipe_type = bool(re.search(r'\b(tubing|drill\s*pipe|workstring|tuber[ií]a|dp|tbg)\b', t_lower))
        has_od = bool(re.search(r'\b(?:2-3/8|2-7/8|3-1/2|4-1/2|5)\b|\d(?:-\d/\d)?"', text))
        has_wt = bool(re.search(r'\d+(?:\.\d+)?\s*(?:lb/ft|#)', text, re.IGNORECASE))
        has_grade = bool(re.search(r'\b(l-?80|n-?80|j-?55|p-?110|13cr)\b', t_lower))
        has_thread = bool(re.search(r'\b(eue|nue|8rd|10rd|ph-?6|hydril|premium|box\s*x\s*pin)\b', t_lower))

        specs_count = sum([has_pipe_type, has_od, has_wt, has_grade, has_thread])
        if specs_count >= 4:
            score += 20
            checks.append("✅ Especificación técnica de tubular completa: Tipo, OD, peso nominal, grado de acero y conexión")
        elif specs_count >= 2:
            score += 10
            missing_specs = []
            if not has_pipe_type: missing_specs.append("tipo (Tubing/Drill Pipe)")
            if not has_od: missing_specs.append("diámetro (ej. 3-1/2\")")
            if not has_wt: missing_specs.append("peso (ej. 9.3 lb/ft)")
            if not has_grade: missing_specs.append("grado (ej. L-80/N-80)")
            if not has_thread: missing_specs.append("rosca (ej. EUE 8RD)")
            missing_for_next_level.append(f"Completar tubular: {', '.join(missing_specs)}")
        else:
            missing_for_next_level.append("Especificación técnica de tubular (Tipo, OD, peso lb/ft, grado y rosca)")

        # 4. Pesos en movimiento: Subiendo (SWU/PUW) y Bajando (SWD/SOW) + Arrastre (Drag)
        has_swu = bool(re.search(r'\b(?:swu|puw|peso\s+subiendo)\b', t_lower))
        has_swd = bool(re.search(r'\b(?:swd|sow|peso\s+bajando)\b', t_lower))
        has_general_wt = bool(re.search(r'\b(?:klb|tension[oó]|peso\s+neutro|overpull)\b', t_lower))
        if has_swu and has_swd:
            score += 15
            checks.append("✅ Control de pesos dinámicos: SWU (subiendo) y SWD (bajando) para auditoría de arrastre (drag)")
        elif has_swu or has_swd or has_general_wt:
            score += 10
            missing_for_next_level.append("Registrar ambos pesos dinámicos: SWU (subiendo) y SWD (bajando) para monitorear arrastre")
        else:
            missing_for_next_level.append("Pesos de sarta en movimiento (SWU subiendo y SWD bajando en klb)")

        # 5. Modo de maniobra (sencillos a rack vs dobles/stands a peine)
        has_mode = bool(re.search(r'\b(sencillos|dobles|stands|paradas|quebrando|rack|peine)\b', t_lower))
        if has_mode:
            score += 10
            checks.append("✅ Modo de maniobra especificado (sencillos a rack / dobles a peine)")
        else:
            missing_for_next_level.append("Modo de maniobra (quebrando en sencillos a rack o paradas en dobles a peine)")

        # 6. Control de pozo y reposición de desplazamiento (API RP 59)
        has_fill = bool(re.search(r'\b(tuber[ií]a\s+llena|tuber[ií]a\s+seca|llenando\s+pozo|tanque\s+de\s+viaje|trip\s*tank|desplazamiento|reemplazando|pozo\s+lleno)\b', t_lower))
        if has_fill:
            score += 15
            checks.append("✅ Control de pozo en viaje (API RP 59): Condición de sarta (llena/seca) y reposición en trip tank")
        else:
            missing_for_next_level.append("Control de llenado de pozo (API RP 59): Tubería llena/seca y monitoreo de trip tank")

        # 7. Velocidad operacional (ft/h o jtas/h)
        has_speed = bool(re.search(r'\b(?:ft/h|ft/hr|jtas/h|jtas/hr|jts/h|vel\s*:)\b', t_lower))
        if has_speed:
            score += 10
            checks.append("✅ Velocidad de viaje calculada y documentada (ft/h o jtas/h)")

    # -----------------------------------------------------------------
    # DOMAIN 5: Fallback General Operations
    # -----------------------------------------------------------------
    else:
        has_od = bool(re.search(r'\d(?:-\d/\d)?"|\d\.\d+"', text))
        has_wt = bool(re.search(r'\d+(?:\.\d+)?\s*(?:lb/ft|#)', text, re.IGNORECASE))
        if has_od and has_wt:
            score += 20
            checks.append("✅ Diámetro exterior y peso nominal especificados (ej. 3-1/2\" 9.3#)")
        elif has_od:
            score += 10
            missing_for_next_level.append("Peso nominal de la tubería (ej. 9.3 lb/ft)")
        else:
            missing_for_next_level.append("Diámetro exterior y peso nominal (ej. 2-7/8\" 6.4#)")

        has_grade = bool(re.search(r'\b(l-?80|n-?80|j-?55|p-?110|13cr)\b', t_lower))
        if has_grade:
            score += 15
            checks.append("✅ Grado metalúrgico de acero especificado (L-80 / N-80 / J-55)")
        else:
            missing_for_next_level.append("Grado de acero del tubular (ej. L-80 o N-80)")

        has_thread = bool(re.search(r'\b(eue|nue|8rd|10rd|tenaris|vam|premium|box\s*x\s*pin)\b', t_lower))
        if has_thread:
            score += 15
            checks.append("✅ Tipo de conexión y rosca especificado (EUE 8RD / Tenaris / VAM)")
        else:
            missing_for_next_level.append("Tipo de rosca y conexión (ej. EUE 8RD)")

        has_range = bool(re.search(r'\b(rango\s*2|range\s*2|r-?2|sencillos|stands)\b', t_lower))
        if has_range:
            score += 10
            checks.append("✅ Rango de longitud y tipo de maniobra especificado (Rango 2 en sencillos)")
        else:
            missing_for_next_level.append("Rango de longitud (ej. Rango 2)")

        has_speed = bool(re.search(r'\b(?:ft/h|ft/hr|jts/h|jts/hr|bpm|ft/min)\b', t_lower))
        if has_speed:
            score += 10
            checks.append("✅ Velocidades operacionales cuantificadas (ft/hr, jts/hr o bpm)")
        else:
            missing_for_next_level.append("Velocidad de corrida en ft/hr o tasa en bpm")

        has_weights = bool(re.search(r'\b(?:swu|swd|swn|puw|sow|overpull|klb|psi)\b', t_lower))
        if has_weights:
            score += 15
            checks.append("✅ Registro de pesos de sarta y presiones (PUW / SOW / klb / psi)")
        else:
            missing_for_next_level.append("Pesos de sarta (PUW / SOW) o presiones de bombeo")

    final_score = min(score, 100)
    
    if final_score < 45:
        tier_label = "Nivel 1: Básico (Informativo)"
        tier_color = "#f59e0b" # amber
    elif final_score < 80:
        tier_label = f"Nivel 2: Estándar ({classification['icon']} {classification['domain'].replace('_', ' ').title()})"
        tier_color = "#38bdf8" # cyan
    else:
        tier_label = f"Nivel 3: Élite ({classification['icon']} Cumplimiento Integral de Operación)"
        tier_color = "#10b981" # emerald

    return {
        "domain": domain,
        "specialist": classification["specialist"],
        "domain_title": classification["title"],
        "score_percent": final_score,
        "tier_label": tier_label,
        "tier_color": tier_color,
        "positive_checks": checks,
        "missing_for_next_level": missing_for_next_level
    }
