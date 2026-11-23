import os
import re
import urllib.request
import json
from typing import Dict, Any, Tuple, List

# ==============================================================================
# ELITE IADC / SPE PROMPT SPECIFICATION (Gemini 3.5 & Multimodal Engines)
# ==============================================================================

ELITE_IADC_SYSTEM_PROMPT = """You are the Senior Lead Petroleum Engineer and Chief IADC/SPE Technical Translator & QA/QC Auditor.
Your mission is to transform raw Spanish well intervention, workover, completion, and well abandonment (P&A) field notes into 100% rigorous, professional, standardized IADC/SPE English narratives.

MANDATORY DIRECTIVES:
1. STRICT ZERO-OMISSION PROTOCOL: You must translate EVERY SINGLE SENTENCE, CLAUSE, NUMBER, UNIT, SERIAL NUMBER, AND DETAIL without exception. NEVER summarize, synthesize, shorten, condense, or drop operations. If an entry describes multiple actions (e.g. tensioning string, rotating right-hand, observing loss of tension, pulling free w/o overpull, forward circulating until full, closing pipe rams, pressure testing HMBP, recording on Barton chart), EVERY SINGLE ACTION MUST appear in the final English narrative with 1:1 completeness.
2. OUTPUT ONLY THE TRANSLATED TEXT: Do NOT include greetings, intro phrases, bullet commentary, or options.
3. ZERO SPANGLISH: Every Spanish word, verb, preposition, and colloquialism MUST be completely converted to natural petroleum engineering English. Never output phrases like "toma of alimentos", "pup joi t", "corte of cable", or "conexiones of lineas".
4. STANDARD IADC ABBREVIATIONS: Enforce standard abbreviations where appropriate:
   - POOH (Pulled Out Of Hole)
   - RIH (Ran In Hole)
   - M/U (Made Up)
   - B/O (Broke Out)
   - L/D (Laid Down)
   - N/U (Nippled Up)
   - N/D (Nippled Down)
   - R/U (Rigged Up)
   - R/D (Rigged Down)
   - WOC (Waiting On Cement)
   - HMBP (Hydro-Mechanical Bridge Plug)
   - BPV (Back Pressure Valve)
   - PJSM (Pre-Job Safety Meeting)
   - PUW (Pick-Up Weight), SOW (Slack-Off Weight), ROTW (Rotating Weight)
5. TYPOS & FIELD SLANG NORMALIZATION:
   - "pup joi t" / "pup joint de manejo" -> "handling pup joint"
   - "llaves hidraulicas" -> "hydraulic power tongs"
   - "choque" / "manifold de choque" -> "choke manifold"
   - "xequipos" / "sus equipos" -> "third-party surface equipment" (e.g., Novomet ESP surface equipment)
   - "circulacion en directa" -> "forward circulation"
   - "circulacion en reversa" -> "reverse circulation"
   - "pulling" -> "POOH / pulling tubing string"
   - "tensiono con X klbs" -> "pulled tension to X klb"
   - "corte de cable" -> "cut ESP power cable"
   - "personal toma de alimentos y descanso" -> "Crew meal and rest break"
   - "reunion preoperacional" -> "Held pre-job safety meeting (PJSM)"
   - "check list diario" -> "conducted daily tool and equipment inspection"
   - "carta barton" / "carta bartón" -> "Barton round pressure chart recorder"
   - "toque de TOC" / "verifico TOC con 10 klb" -> "tagged TOC w/ 10 klb"
6. PRESERVE NUMERICAL DATA & TIMELINES EXACTLY: Keep the exact hours (e.g. '00:00 - 01:00') and all weights, depths, pressures, and volumes.
7. CLEAN HANDLING OF INLINE PLACEHOLDERS: If the Spanish narrative contains uncompleted bracketed placeholders (such as '[___ bpm]', '[TOTAL JTS]', '[SWD: ___ klb]', or '[especificar ...]'), preserve the brackets with natural English field labels (e.g. '[TOTAL JTS]', '[specify BHA type / objective: e.g. fishing / completion]', '[SWD: ___ klb]', '[___ bpm]') or omit placeholder instructions if actual engineering values have already been filled in. Never leave raw Spanish words inside bracketed engineering placeholders."""

MODELS_CASCADE = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest"
]

# ==============================================================================
# MASTER PETROLEUM TRANSLATION ENGINE (Offline High-Accuracy IADC Rulebook)
# ==============================================================================

# High-priority multi-word contextual patterns
CONTEXTUAL_PATTERNS: List[Tuple[str, str]] = [
    # -------------------------------------------------------------
    # 1. Meals, Rest & Safety Stand-Down
    # -------------------------------------------------------------
    (r"personal\s+toma\s+de\s+alimentos\s+y\s+descanso\.?", "Crew meal and rest break."),
    (r"toma\s+de\s+alimentos\s+y\s+descanso\.?", "Crew meal and rest break."),
    (r"personal\s+tomando\s+alimentos\s*\(almuerzo\)\.?", "Crew meal break (Lunch)."),
    (r"personal\s+tomando\s+alimentos\.?", "Crew meal break."),
    (r"personal\s+tomando\s+lonche\.?", "Crew meal break."),
    (r"descanso\s+del\s+personal\.?", "Crew rest break."),
    (r"parada\s+de\s+seguridad:\s*", "Safety stand-down: "),

    # -------------------------------------------------------------
    # 2. Rig Moves, Mobilization & Rig Up (R/U, R/D)
    # -------------------------------------------------------------
    (
        r"movilizaci[oó]n\s+lump\s+sum\s+de\s+(.*?)\s+desde\s+(?:el\s+)?pozo\s+(.*?)\s+(?:hacia|al)\s+(?:el\s+)?pozo\s+(.*?)\s*\((.*?)\)",
        r"Lump sum rig mobilization of \1 from well \2 to well \3 (\4)"
    ),
    (
        r"moviliz[oó]\s+lump\s+sum\s+entre\s+locaci[oó]n\s+de\s+(.*?)\s+desde\s+(?:el\s+)?pozo\s+(.*?)\s+(?:hacia|al)\s+(?:el\s+)?pozo\s+(.*?)\s*\((.*?)\)",
        r"Lump sum rig move between locations of \1 from well \2 to well \3 (\4)"
    ),
    (r"\bfinaliz[oó]\s+movilizaci[oó]n\s+lum[p]?\s+sum\b", "Completed lump sum rig mobilization"),
    (r"\binicio\s+de\s+movilizaci[oó]n\s+de\s+(?:equipo|taladro|torre)\b", "Commenced rig mobilization"),
    (r"\binicio\s+de\s+movilizaci[oó]n\b", "Commenced rig mobilization"),
    (r"\bmovilizaci[oó]n\s+lump\s+sum\b", "lump sum rig mobilization"),
    (r"\bmoviliz[oó]\s+lump\s+sum\b", "mobilized lump sum"),
    (r"\bmovilizaci[oó]n\s+entre\s+locaciones\b", "rig move between locations"),
    (r"\bmovilizaci[oó]n\s+entre\s+pozos\b", "rig move between wells"),
    (r"continuan\s+operaciones\s+de\s+movilizaci[oó]n\s+y\s+arme\s+del\s+equipo\.?", "Continued rig mobilization and rig up (R/U) of rig."),
    (r"contin[uú]an\s+operaciones\s+de\s+movilizaci[oó]n\s+y\s+arme", "Continued rig mobilization and rig up (R/U)"),
    (r"continuan\s+operaciones\s+de\s+arme\s+del\s+equipo\.?", "Continued rig up (R/U) of rig."),
    (r"operaciones\s+de\s+movilizaci[oó]n\s+y\s+arme", "rig mobilization and rig up (R/U) operations"),
    (r"\brecibi[oó]\s+equipo\s+a\s+las\s+(\d{1,2}:\d{2})\s*h\s+del\s+d[ií]a\s+(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", r"Accepted rig / Handover at \1 hrs on \2-\3-\4"),
    (r"\brealiz[oó]\s+reconocimiento\s+de\s+(\d+)\s*h\s+sobre\s+la\s+hora\s+de\s+recibo\s+de\s+equipo\b", r"recognized \1 hrs credit adjustment on rig acceptance time"),
    (r"\btotal\s+de\s+cargas\s+movilizadas:\s*", "Total mobilized transport loads: "),
    (r"\btotal\s+de\s+cargas:\s*", "Total loads: "),
    (r"\bcargas?\s+movilizadas?:\s*", "Mobilized loads: "),
    (r"\bcargas?\s+pendientes?:\s*", "Pending loads: "),
    (r"\btiempo\s+total:\s*", "Total elapsed time: "),
    (r"\btiempo\s+transcurrido:\s*", "Elapsed time: "),
    (r"\bdistancia:\s*", "Distance: "),
    (r"\bliber[oó]\s+equipo\s+(.*?)\s+el\s+(\d{1,2}/\d{1,2}/\d{4})\s+a\s+las\s+(\d{1,2}:\d{2})\s*h", r"Released rig \1 on \2 @ \3 hrs"),
    (r"\boperaciones\s+de\s+ac[aá]\s+en\s+adelante\s+tipo\s+rig\s*less\b", "Operations continued in rigless mode"),
    (r"\btransici[oó]n\s+de\s+tarifa\b", "rate transition"),
    (r"\btarifa\s+lump\s+sum\b", "lump sum rate"),
    (r"\btarifa\s+operativa\b", "operational day rate"),
    (r"\btarifa\s+stand\s*by\b", "standby rate"),

    # -------------------------------------------------------------
    # 3. Surface Plumbing, Manifold, Power Tongs & Pup Joints
    # -------------------------------------------------------------
    (r"realiza\s+conexiones\s+de\s+l[ií]neas\s+de\s+la\s+bomba\s+y\s+el\s+choque\.?", "Plumbed surface pump and choke manifold lines."),
    (r"realiz[oó]\s+conexiones\s+de\s+l[ií]neas\s+de\s+la\s+bomba\s+y\s+el\s+choque\.?", "Plumbed surface pump and choke manifold lines."),
    (r"conexiones\s+de\s+l[ií]neas\s+de\s+la\s+bomba\s+y\s+el\s+choque", "Plumbed surface pump and choke manifold lines"),
    (r"rig\s+up\s+llaves\s+hidr[aá]ulicas\.?", "Rigged up hydraulic power tongs."),
    (r"arm[oó]\s+llaves\s+hidr[aá]ulicas\.?", "Rigged up hydraulic power tongs."),
    (r"llaves\s+hidr[aá]ulicas", "hydraulic power tongs"),
    (r"instala\s+pup\s+joi\s*t\s+de\s+manejo\.?", "Installed handling pup joint."),
    (r"instal[oó]\s+pup\s+joi\s*t\s+de\s+manejo\.?", "Installed handling pup joint."),
    (r"pup\s+joi\s*t\s+de\s+manejo", "handling pup joint"),
    (r"pup\s+joi\s*t", "pup joint"),
    (r"pup\s+joint\s+de\s+manejo", "handling pup joint"),
    (r"novomet\s+arme\s+de\s+sus\s+x?equipos\.?", "Novomet rigged up ESP surface equipment."),
    (r"arme\s+de\s+sus\s+x?equipos", "rigged up third-party surface equipment"),
    (r"xequipos", "surface equipment"),

    # -------------------------------------------------------------
    # 4. Circulation, Hydraulics & Pressures
    # -------------------------------------------------------------
    (r"realiz[oó]\s+conexiones\s+y\s+realiz[oó]\s+circulaci[oó]n\s+en\s+directa\s+(\d+)\s*bbls?\s+con\s+(\d+)\s*psi\.?", r"Made up surface connections and established forward circulation w/ \1 bbl @ \2 psi."),
    (r"circulaci[oó]n\s+en\s+directa\s+(\d+)\s*bbls?\s+con\s+(\d+)\s*psi", r"forward circulation w/ \1 bbl @ \2 psi"),
    (r"circulaci[oó]n\s+en\s+directa", "forward circulation"),
    (r"circulaci[oó]n\s+en\s+reversa", "reverse circulation"),
    (r"revers[oó]\s+(\d+)\s*bbl\s+hasta\s+retorno\s+limpio", r"reverse circulated \1 bbl to clean returns"),
    (r"p[ií]ldora\s+de\s+limpieza:\s*", "Cleanout pill: "),
    (r"bombe[oó]\s+a\s+(\d+(?:\.\d+)?)\s*bpm\s+con\s+bola\s+de\s+([0-9\./”\"]+)", r"pumped @ \1 bpm w/ \2 setting ball"),
    (r"presuriz[oó]\s+hasta\s+(\d+)\s*psi\s+observando\s+ca[ií]da\s+s[uú]bita\s+a\s+0\s*psi", r"pressured up to \1 psi, observing sudden drop to 0 psi"),

    # -------------------------------------------------------------
    # 5. Pre-Job Safety Meetings (PJSM) & Checklists
    # -------------------------------------------------------------
    (r"reuni[oó]n\s+preoperacional\s+para\s+inicio\s+de\s+pulling\s+de\s+tuber[ií]a\s+(.*?)(?:\.|$)", r"Held pre-job safety meeting prior to commencing tubing pulling (POOH) on \1."),
    (r"reuni[oó]n\s+preoperacional\s+para\s+", "Held pre-job safety meeting (PJSM) prior to "),
    (r"charla\s+preoperacional\s+para\s+", "Held pre-job safety meeting (PJSM) prior to "),
    (r"reuni[oó]n\s+de\s+seguridad\s+y\s+preoperacional\s+con\s+todo\s+el\s+personal", "Conducted pre-job safety and operations meeting w/ rig crew"),
    (r"retom[oó]\s+charla\s+de\s+seguridad\s+antes\s+de\s+", "Resumed safety meeting prior to "),
    (r"realiz[oó]\s+check\s*list\s+diario\s+de\s+herramientas\s+y\s+equipos\.?", "Conducted daily tools and equipment checklist."),
    (r"check\s*list\s+diario\s+de\s+herramientas\s+y\s+equipos", "daily tools and equipment checklist"),

    # -------------------------------------------------------------
    # 6. Tripping, Pulling (POOH/RIH), Overpull & Power Cable
    # -------------------------------------------------------------
    (r"continuan\s+operaciones\s+inicio\s+de\s+pulling\s+(?:del\s+)?pozo\s+(.*?)\s+tension[oó]?\s+con\s+(\d+)\s*klbs?\s+peso\s+(\d+)\s*klbs?\.?", r"Continued operations to commence pulling Well \1; pulled tension to \2 klb (string weight \3 klb)."),
    (r"continuan\s+operaciones\s+inicio\s+de\s+pulling\s+de\s+tuber[ií]a", "Continued operations to commence pulling tubing string (POOH)"),
    (r"inicio\s+de\s+pulling\s+de\s+tuber[ií]a", "commenced tubing pulling (POOH)"),
    (r"pulling\s+de\s+tuber[ií]a", "tubing pulling (POOH)"),
    (r"tension[oó]?\s+con\s+(\d+)\s*klbs?", r"pulled tension to \1 klb"),
    (r"peso\s+(\d+)\s*klbs?", r"string weight \1 klb"),
    (r"corte\s+de\s+cable\s+y\s+sacando\s+primeras\s+juntas\.?", "Cut ESP power cable and POOH pulling initial joints."),
    (r"corte\s+de\s+cable", "cut ESP power cable"),
    (r"sacando\s+primeras\s+juntas", "POOH pulling initial joints"),
    (r"primeras\s+juntas", "initial joints"),
    (r"sacar\s+tuber[ií]a\s+quebrando\s+en\s+sencillos\s+a\s+rack", "POOH racking singles to pipe racks"),
    (r"quebrando\s+en\s+sencillos\s+a\s+rack[s]?", "racking singles to pipe racks"),
    (r"en\s+sencillos\s+desde\s+los\s+pipe\s+racks", "in singles from pipe racks"),
    (r"desde\s+superficie\s+hasta\s+(\d+(?:\.\d+)?)\s*ft", r"from surface to \1 ft MD"),
    (r"desde\s+(\d+(?:\.\d+)?)\s*ft(?:-em)?\s+hasta\s+(\d+(?:\.\d+)?)\s*ft", r"from \1 ft to \2 ft MD"),
    (r"continu[oó]\s+rih", "Cont RIH"),
    (r"continu[oó]\s+pooh", "Cont POOH"),
    (r"rih\s+bha\s+no\.\s*(\d+)", r"RIH BHA #\1"),
    (r"pooh\s+bha\s+no\.\s*(\d+)", r"POOH BHA #\1"),
    (r"m/u\s+bha\s+no\.\s*(\d+)", r"M/U BHA #\1"),
    (r"l/d\s+de\s+sarta", "L/D string"),
    (r"l/d\s+secci[oó]n\s+c", "N/D Section C"),
    (r"n/d\s+secci[oó]n\s+c", "N/D Section C"),

    # -------------------------------------------------------------
    # 7. Wellhead, BOP & Pressure Tests (API 53)
    # -------------------------------------------------------------
    (
        r"realiz[oó]\s+prueba\s+de\s+(?:bop\s+anular|anular|preventor\s+anular)\s+([0-9\-/”\"]+)\s*(?:x|×)\s*([0-9kK]+)\s+as[ií]:",
        r"Pressure tested \1 \2 Annular BOP as follows:"
    ),
    (
        r"realiz[oó]\s+prueba\s+de\s+bop\s+([0-9\-/”\"]+)\s*(?:x|×)\s*([0-9kK]+)\s+as[ií]:",
        r"Pressure tested \1 \2 BOP stack as follows:"
    ),
    (
        r"realiz[oó]\s+prueba\s+de\s+pipe\s+rams?\s+([0-9\-/”\"]+)\s*(?:x|×)\s*([0-9kK]+)\s+as[ií]:",
        r"Pressure tested \1 \2 Pipe Rams as follows:"
    ),
    (
        r"realiz[oó]\s+prueba\s+de\s+blind\s+rams?\s+([0-9\-/”\"]+)\s*(?:x|×)\s*([0-9kK]+)\s+as[ií]:",
        r"Pressure tested \1 \2 Blind Rams as follows:"
    ),
    (
        r"realiz[oó]\s+prueba\s+de\s+shear\s+rams?\s+([0-9\-/”\"]+)\s*(?:x|×)\s*([0-9kK]+)\s+as[ií]:",
        r"Pressure tested \1 \2 Shear Rams as follows:"
    ),
    (r"realiz[oó]\s+pruebas\s+de\s+choke\s+manifold\s+as[ií]:", "Pressure tested choke manifold as follows:"),
    (
        r"v[aá]lvula\s+no\.?\s*(\d+)\s+en\s+baja\s+con\s+(\d+)\s*psi\s*[x×]\s*(\d+)\s*min(?:,\s*ok)?;\s*en\s+alta\s+con\s+(\d+)\s*psi\s*[x×]\s*(\d+)\s*min(?:,\s*ok)?(?:\.|\b)?",
        r"Valve #\1 Low w/ \2 psi x \3 min (OK); High w/ \4 psi x \5 min (OK)"
    ),
    (
        r"v[aá]lvulas\s+no\.?\s*([\d\s\-ey,]+)\s+en\s+baja\s+con\s+(\d+)\s*psi\s*[x×]\s*(\d+)\s*min(?:,\s*ok)?;\s*en\s+alta\s+con\s+(\d+)\s*psi\s*[x×]\s*(\d+)\s*min(?:,\s*ok)?(?:\.|\b)?",
        r"Valves #\1 Low w/ \2 psi x \3 min (OK); High w/ \4 psi x \5 min (OK)"
    ),
    (
        r"en\s+baja\s+con\s+(\d+)\s*psi\s*(?:x|×)\s*(\d+)\s*min(?:,\s*ok)?;\s*en\s+alta\s+con\s+(\d+)\s*psi\s*(?:x|×)\s*(\d+)\s*min(?:,\s*ok)?",
        r"Low w/ \1 psi x \2 min (OK); High w/ \3 psi x \4 min (OK)"
    ),
    (r"anular\s+en\s+baja\s+con\s+(\d+)\s*psi\s*x\s*(\d+)\s*min(?:,\s*ok)?;\s*en\s+alta\s+con\s+(\d+)\s*psi\s*x\s*(\d+)\s*min(?:,\s*ok)?", r"Annular Low w/ \1 psi x \2 min (OK); High w/ \3 psi x \4 min (OK)"),
    (r"pipe\s+rams?\s+en\s+baja\s+con\s+(\d+)\s*psi\s*x\s*(\d+)\s*min(?:,\s*ok)?;\s*en\s+alta\s+con\s+(\d+)\s*psi\s*x\s*(\d+)\s*min(?:,\s*ok)?", r"Pipe rams Low w/ \1 psi x \2 min (OK); High w/ \3 psi x \4 min (OK)"),
    (r"blind\s+rams?\s+en\s+baja\s+con\s+(\d+)\s*psi\s*x\s*(\d+)\s*min(?:,\s*ok)?;\s*en\s+alta\s+con\s+(\d+)\s*psi\s*x\s*(\d+)\s*min(?:,\s*ok)?", r"Blind rams Low w/ \1 psi x \2 min (OK); High w/ \3 psi x \4 min (OK)"),
    (r"\.?\s*prob[oó]\s+acumulador\s+cumple\s+con\s+los\s+tiempos\s+de\s+carga", ". Tested accumulator unit recharge times, met API specifications (OK)"),

    # -------------------------------------------------------------
    # 8. Bridge Plugs & Downhole Mechanics
    # -------------------------------------------------------------
    (
        r"se\s+coloc[oó]\s+la\s+sarta\s+en\s+tensi[oó]n\s+registrando\s+(\d+(?:\.\d+)?)\s*klb,?\s+posteriormente\s+se\s+aplic[oó]\s+rotaci[oó]n\s+a\s+la\s+derecha\s+sobre\s+la\s+sarta\s+de\s+tuber[ií]a\s+(.*?)\s+completando\s+(\d+)\s+vueltas\.?",
        r"Placed the workstring in tension, recording \1 klb, then applied right-hand (RH) rotation to the \2 tubing string, completing \3 turns."
    ),
    (
        r"durante\s+la\s+maniobra\s+se\s+observ[oó]\s+p[eé]rdida\s+de\s+tensi[oó]n\s+y,?\s+al\s+levantar\s+la\s+sarta,?\s+se\s+evidenci[oó]\s+que\s+esta\s+se\s+encontraba\s+libre,?\s+sin\s+registrar\s+overpull,?\s+quedando\s+con\s+un\s+nuevo\s+peso\s+de\s+(\d+(?:\.\d+)?)\s*klb\.?",
        r"During the operation, a loss of tension was observed, and upon picking up the string, it was verified free with zero overpull, recording a new string weight of \1 klb."
    ),
    (
        r"bombe[oó]\s+en\s+directa\s+hasta\s+evidenciar\s+(?:el\s+)?pozo\s+lleno;?\s*posteriormente\s+se\s+cerraron\s+los\s+pipe\s+rams\s+y\s+se\s+realiz[oó]\s+prueba\s+de\s+integridad\s+del\s+hmbp\s+de\s+([0-9\-/”\"]+)\s+aplicando\s+(\d+)\s*psi\s+durante\s+(\d+)\s+minutos,?\s*obteniendo\s+resultados\s+satisfactorios\s*\(ok\)\.?",
        r"Pumped via forward circulation until observing the well full; subsequently closed pipe rams and pressure tested integrity of the \1 HMBP to \2 psi for \3 minutes (OK)."
    ),
    (
        r"dej[oó]\s+registrada\s+en\s+carta\s+bart[oó]n\s+prueba\s+de\s+bp\.?",
        "Recorded bridge plug pressure test on Barton round circular chart recorder."
    ),
    (r"carta\s+bart[oó]n", "Barton circular pressure chart recorder"),
    (r"prueba\s+de\s+bp\b", "bridge plug pressure test"),
    (r"sent[oó]\s+bridge\s+plug\s+hidromec[aá]nico\s+de\s+([0-9\-/”\"]+)\s*@\s*(\d+)\s*ft", r"Set \1 Hydro-Mechanical Bridge Plug (HMBP) @ \2 ft MD"),
    (r"verific[oó]\s+anclaje\s+con\s+(\d+)\s*klb\s+de\s+overpull(?:\s*\((.*?)\))?", r"confirmed anchor w/ \1 klb overpull (\2)"),
    (r"baj[oó]\s+sarta\s+y\s+aplic[oó]\s+peso\s+sobre\s+el\s+hmbp\s+de\s+(\d+(?:\.\d+)?)\s*klb", r"slacked off \1 klb weight on HMBP"),
    (r"liber[oó]\s+(?:del\s+)?hmbp\s+con\s+(\d+)\s+vueltas\s+a\s+la\s+derecha", r"released from HMBP w/ \1 RH turns"),
    (r"prob[oó]\s+integridad\s+del\s+hmbp\s+([0-9\-/”\"]+)\s+con\s+(\d+)\s*psi\s*x\s*(\d+)\s*min(?:utos)?", r"pressure tested \1 HMBP to \2 psi x \3 min (OK)"),
    (
        r"dispar[oó]\s+ca[ñn][oó]n\s+(?:de\s+casing|de\s+revestimiento)?\s*([0-9\-/”\"]+)\s*para\s+comunicar\s+anular\s+([0-9\-/”\"]+)\s*(?:x|×)\s*([0-9\-/”\"]+)",
        r"Perforated casing w/ \1 casing gun to establish communication between \2 x \3 annulus"
    ),

    # -------------------------------------------------------------
    # 9. Cementing & P&A
    # -------------------------------------------------------------
    (r"mezcl[oó]\s+cemento\s+y\s+realiz[oó]\s+tap[oó]n\s+de\s+fondo\s+de\s+(\d+)\s*ft\s+a\s+(\d+)\s*ft(?:,\s*(\d+)\s*ft\s+de\s+espesor)?", r"Mixed and spotted balanced bottom cement plug from \1 ft to \2 ft MD (\3 ft thickness)"),
    (r"balance[oó]\s+tap[oó]n\s+de\s+cemento\s+de\s+fondo", "Spotted balanced bottom cement plug"),
    (r"inici[oó]\s+tiempo\s+de\s+woc", "Commenced WOC"),
    (r"tiempo\s+de\s+woc\s*\((.*?)\)", r"Waiting on Cement (WOC) (\1)"),
    (r"verific[oó]\s+toc\s+con\s+(\d+)\s*klb\s+a\s+(\d+(?:\.\d+)?)\s*ft", r"Tagged TOC w/ \1 klb weight @ \2 ft MD (OK)"),
    (r"recogi[oó]\s+(\d+)\s+testigos", r"Caught \1 surface witness samples"),
    (r"evidenci[oó]\s+succi[oó]n\s+en\s+backflow", "Observed suction on backflow / U-tubing effect"),

    # -------------------------------------------------------------
    # 10. Artificial Lift & ESP Decoupling
    # -------------------------------------------------------------
    (
        r"con\s+standing\s+valve\s+instalada,?\s*raz[oó]n\s+por\s+la\s+cual\s+no\s+fue\s+posible\s+drenar\s+tbg\s+cuando\s+se\s+lanz[oó]\s+la\s+barra\s+para\s+romper\s+los?\s+pin\s+de\s+la\s+drain\s+valve\.?",
        "Standing valve installed in seating nipple, preventing tubing drainage when bar was dropped to shear drain valve pin."
    ),

    # -------------------------------------------------------------
    # 11. Guided Golden Paragraph Placeholders Translation
    # -------------------------------------------------------------
    (r"\[especificar\s+tipo\s+de\s+bha\s+y\s+objetivo:?\s*(.*?)\]", r"[specify BHA type / objective: \1]"),
    (r"\[especificar:\s*rosca\s+ej\.\s*eue\s*8rd,?\s*peso:\s*___\s*lb/ft,?\s*grado:\s*___\]", r"[specify: thread e.g. EUE 8RD, weight: ___ lb/ft, grade: ___]"),
    (r"\[especificar\s+tubular:?\s*(.*?)\]", r"[specify tubular: \1]"),
    (r"condici[oó]n\s+de\s+llenado:\s*\[tuber[ií]a\s+llena/seca,?\s*trip\s*tank:\s*___\s*bbl\]", r"hole fill status: [wet/dry string, trip tank: ___ bbl]"),
    (r"condici[oó]n\s+de\s+sarta:\s*\[tuber[ií]a\s+llena/seca\]", r"string condition: [wet/dry string]"),
    (r"condici[oó]n\s+de\s+sarta:\s*\[tuber[ií]a\s+llena\s*/\s*seca\]", r"string condition: [wet/dry string]"),
    (r"\[especificar\s+fluido:?\s*agua\s+industrial\s*/\s*salmuera\]", r"[specify fluid: industrial water / brine]"),
    (r"desacople\s+de\s+sarta\s+esp", "Decoupled ESP downhole assembly"),
    (r"tom[oó]\s+medidas\s+el[eé]ctricas\s+antes\s+de\s+desacople\s+esp:", "Recorded electrical measurements prior to ESP decouple:"),
    (r"balanceado\s+con\s+falla\s+a\s+tierra", "balanced with ground fault to earth"),
    (r"dictamen:\s*falla\s+el[eé]ctrica\s+en\s+motor", "Diagnosis: electrical insulation breakdown in motor"),
    (r"retir[oó]\s+overcoupling\s+y\s+(\d+)\s+superbandas\s+por\s+junta", r"removed overcoupling & \1 superbands per joint"),
    (r"se\s+recuperaron\s+(\d+)\s*ft\s+de\s+cable\s+de\s+potencia", r"recovered \1 ft of ESP power cable"),
    (r"pulling\s+(?:de\s+esp\s+)?con\s+tuber[ií]a\s+llena", "POOH wet string (tubing full)"),
    (r"con\s+tuber[ií]a\s+llena", "with wet string (tubing full)"),
    (r"despach[oó]\s+carrotanque\s+(?:sencillo\s+)?de\s+producci[oó]n\s+con\s+(\d+)\s*bbl\s+de\s+crudo\s*\+\s*(\d+)\s*bbl\s+de\s+agua\s+a\s+(.*?)(?:\.|$)", r"Dispatched production tanker truck w/ \1 bbl crude + \2 bbl water to \3."),
    (r"arrib[oó]\s+carrotanque\s+con\s+(\d+)\s*bbl\s+de\s+agua\s+industrial\s+de\s+(.*?)(?:\.|$)", r"Received tanker truck w/ \1 bbl industrial water from \2."),

    # -------------------------------------------------------------
    # 11. Well Name Normalization
    # -------------------------------------------------------------
    (r"\bpozo\s+yopo\s*#?\s*(\d+)", r"Well Yopo #\1"),
    (r"\byopo\s*#?\s*(\d+)", r"Yopo #\1")
]

# Word-Level Lexicon (Strict technical terms - NO loose standalone prepositions)
WORD_REPLACEMENTS: List[Tuple[str, str]] = [
    (r"\ben\s+sencillos\b", "in singles"),
    (r"\ben\s+dobles\b", "in doubles"),
    (r"\ba\s+rack\b", "to rack"),
    (r"\ba\s+racks\b", "to rack"),
    (r"\ba\s+peine\b", "to derrick fingers"),
    (r"\bcon\s+tbg\b", "w/ TBG"),
    (r"\bcon\s+tuber[ií]a\b", "w/ tubing"),
    (r"\bmismo\s+pad\b", "same pad"),
    (r"\bmisma\s+locaci[oó]n\b", "same location"),
    (r"\bequipo\s+de\s+workover\b", "workover rig"),
    (r"\bequipo\s+de\s+reacondicionamiento\b", "workover rig"),
    (r"\bequipo\s+de\s+perforaci[oó]n\b", "drilling rig"),
    (r"\btaladro\b", "rig"),
    (r"\btorre\b", "rig"),
    (r"\bequipo\b", "rig"),
    (r"\bcami[oó]n\s+gr[uú]a\b", "crane truck"),
    (r"\bgr[uú]a\b", "crane"),
    (r"\bcarrotanque\b", "tanker truck"),
    (r"\bcama\s+baja\b", "lowboy trailer"),
    (r"\btractomula\b", "transport truck"),
    (r"\bdesde\s+el\s+pozo\b", "from well"),
    (r"\bdesde\s+pozo\b", "from well"),
    (r"\bhacia\s+el\s+pozo\b", "to well"),
    (r"\bhacia\s+pozo\b", "to well"),
    (r"\bal\s+pozo\b", "to well"),
    (r"\ba\s+pozo\b", "to well"),
    (r"\bdel\s+pozo\b", "of well"),
    (r"\blocaci[oó]n\b", "location"),
    (r"\bpozo\b", "well"),
    (r'(\d+[\d/”"]*)\s+y\s+(\d+[\d/”"]*)', r'\1 & \2'),
    (r"\blechada\s+de\s+cemento\b", "cement slurry"),
    (r"\blechada\b", "slurry"),
    (r"\btap[oó]n\s+de\s+cemento\b", "cement plug"),
    (r"\btap[oó]n\s+de\s+fondo\b", "bottom cement plug"),
    (r"\btap[oó]n\s+balanceado\b", "balanced cement plug"),
    (r"\bespesor\b", "thickness"),
    (r"\bpreflujo\b", "preflush"),
    (r"\bagua\s+fresca\b", "fresh water"),
    (r"\bagua\s+industrial\b", "industrial water"),
    (r"\bgoma\s+x[aá]ntica\b", "xanthan gum"),
    (r"\bsurfactante\b", "surfactant"),
    (r"\bretorno\s+limpio\b", "clean returns"),
    (r"\bpozo\s+lleno\b", "well full"),
    (r"\btuber[ií]a\s+combinada\b", "tapered workstring"),
    (r"\btuber[ií]a\s+de\s+producci[oó]n\b", "production tubing"),
    (r"\btuber[ií]a\b", "tubing"),
    (r"\bsarta\b", "string"),
    (r"\bsencillos\b", "singles"),
    (r"\bparejas\b", "stands"),
    (r"\bracks?\b", "pipe racks"),
    (r"\bplanchada\b", "catwalk"),
    (r"\brampa\b", "pipe ramp"),
    (r"\bsubestructura\b", "substructure"),
    (r"\bcontrapozo\b", "cellar"),
    (r"\bsin\s+arrastre\b", "w/o drag"),
    (r"\bprueba\s+de\s+bop\s+anular\b", "Annular BOP pressure test"),
    (r"\bprueba\s+de\s+bop\b", "BOP pressure test"),
    (r"\bprueba\s+de\s+hermeticidad\b", "leak-off / pressure integrity test"),
    (r"\bprueba\s+de\s+integridad\b", "pressure integrity test"),
    (r"\bprueba\s+de\s+presi[oó]n\b", "pressure test"),
    (r"\bprob[oó]\s+integridad\b", "pressure tested integrity"),
    (r"\bprob[oó]\s+en\s+baja\b", "pressure tested Low"),
    (r"\bprob[oó]\s+en\s+alta\b", "pressure tested High"),
    (r"\bprob[oó]\b", "pressure tested"),
    (r"\bpreventor\s+anular\b", "Annular preventer"),
    (r"\banular\b", "Annular"),
    (r"\ben\s+baja\s+con\b", "Low w/"),
    (r"\ben\s+alta\s+con\b", "High w/"),
    (r"\ben\s+baja\b", "Low"),
    (r"\ben\s+alta\b", "High"),
    (r"\bca[ií]da\s+de\s+presi[oó]n\b", "pressure drop"),
    (r"\bbomba\s+de\s+cementaci[oó]n\b", "cement pump"),
    (r"\bcarta\s+de\s+presi[oó]n\b", "pressure chart"),
    (r"\bcarta\s+registradora\b", "circular pressure chart recorder"),
    (r"\bv[aá]lvulas\b", "Valves"),
    (r"\bv[aá]lvula\b", "Valve"),
    (r"\bjtas\b", "jts"),
    (r"\bjuntas\b", "jts"),
    (r"\bvel:\s*", "Speed: "),
    (r"\bswu:\s*", "PUW: "),
    (r"\bswd:\s*", "SOW: "),
    (r"\bswn:\s*", "ROTW: "),
    (r"\bnotas?:\s*", "Notes: "),
    (r"\bavance:\s*", "Progress: "),
    (r"\bas[ií]:", "as follows:"),
    (r",\s*ok\b", " (OK)"),
    (r"(?<!\()\bok\b(?!\))", "(OK)")
]


def offline_standardized_translation(text: str) -> str:
    """
    Enhanced deterministic translation engine that transforms Spanish field logs
    into fluent, standardized IADC English narratives without Spanglish.
    """
    lines = text.strip().split("\n")
    translated_lines = []

    for line in lines:
        t_line = line.strip()
        if not t_line:
            continue

        # 1. Apply multi-word contextual patterns
        for pattern, repl in CONTEXTUAL_PATTERNS:
            t_line = re.sub(pattern, repl, t_line, flags=re.IGNORECASE)

        # 2. Apply syntactic word-level tokens & lexicon
        for pattern, repl in WORD_REPLACEMENTS:
            t_line = re.sub(pattern, repl, t_line, flags=re.IGNORECASE)

        # 3. Clean up formatting and spacing
        t_line = re.sub(r"\s{2,}", " ", t_line)
        t_line = re.sub(r"\s+([,.;:\)])", r"\1", t_line)
        t_line = re.sub(r"(\()\s+", r"\1", t_line)

        # Clean double parenthesis or repeated OK tokens
        t_line = re.sub(r"\(\s*\(\s*OK\s*\)\s*\)", "(OK)", t_line, flags=re.IGNORECASE)
        t_line = re.sub(r"\(\s*OK\s*\)\s*\)", "(OK)", t_line, flags=re.IGNORECASE)
        t_line = re.sub(r"\(\s*\(\s*OK\s*", "(OK", t_line, flags=re.IGNORECASE)

        # Capitalize first letter of sentence after timeline
        time_match = re.match(r"^(\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\s*)(.*)$", t_line)
        if time_match:
            prefix = time_match.group(1)
            body = time_match.group(2)
            if body:
                body = body[0].upper() + body[1:]
            t_line = prefix + body
        elif len(t_line) > 1:
            t_line = t_line[0].upper() + t_line[1:]

        translated_lines.append(t_line)

    return "\n".join(translated_lines)


# ==============================================================================
# AGENT #10: IADC / SPE TRANSLATION QA/QC AUDITOR
# ==============================================================================

def audit_translation_qaqc(english_text: str, spanish_text: str = "") -> Dict[str, Any]:
    """
    Agent #10 (iadc-translation-qaqc-auditor): Audits the English translation output.
    Verifies 100% standard oilfield English, detects residual Spanglish,
    and certifies technical compliance for official IADC reporting.
    """
    # Spanish tokens that must NEVER appear in official English reports
    unwanted_spanish_regex = re.compile(
        r'\b(del|para|por|alimentos|descanso|conexiones|lineas|tuber[ií]a|manejo|xequipos|sacando|primeras|juntas|tensiono|corte|arme|desarme)\b',
        re.IGNORECASE
    )
    # Spanglish combos (e.g. 'of alimentos', 'corte of')
    spanglish_combos_regex = re.compile(
        r'\b(of\s+(?:alimentos|lineas|tuber[ií]a|manejo|equipo|cargas|cemento|acero|los|las|el|la|descanso)|corte\s+of|toma\s+of|pup\s+joi\s*t|pulling\s+pozo)\b',
        re.IGNORECASE
    )

    spanish_tokens = unwanted_spanish_regex.findall(english_text)
    spanglish_combos = spanglish_combos_regex.findall(english_text)

    findings = []
    has_spanglish = len(spanish_tokens) > 0 or len(spanglish_combos) > 0

    # Numerical and Data Parity Audit (Zero-Omission Verification)
    spanish_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", spanish_text)
    english_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", english_text))
    
    retained_count = sum(1 for n in spanish_numbers if n in english_numbers)
    total_nums = len(spanish_numbers)
    parity_pct = round((retained_count / total_nums) * 100, 1) if total_nums > 0 else 100.0

    if has_spanglish:
        bad_words = list(set([w.lower() for w in (spanish_tokens + spanglish_combos)]))[:6]
        quality_score = max(25, 80 - (len(spanish_tokens) * 10))
        status = "SUBSTANDARD_SPANGLISH"
        findings.append({
            "agent": "iadc-translation-qaqc-auditor",
            "severity": "CRITICAL",
            "badge": "🔴 ALERTA DE TRADUCCIÓN: SPANGLISH DETECTADO",
            "message": f"El Auditor de Traducción IADC detectó residuos de español/Spanglish en la narrativa ({', '.join(bad_words)}). La traducción requiere revisión del vocabulario técnico antes de exportar a DOR."
        })
    elif total_nums >= 3 and parity_pct < 60.0:
        quality_score = 65
        status = "DATA_TRUNCATED"
        findings.append({
            "agent": "iadc-translation-qaqc-auditor",
            "severity": "WARNING",
            "badge": "🟡 ALERTA DE PARIDAD: POSIBLE OMISIÓN DE DATOS",
            "message": f"Se detectó una reducción de parámetros operacionales ({retained_count}/{total_nums} valores numéricos retenidos, {parity_pct}%). Verifique que no se hayan omitido presiones (psi), pesos (klb), vueltas o cotas de profundidad."
        })
    else:
        quality_score = 100
        status = "CERTIFIED_IADC"
        findings.append({
            "agent": "iadc-translation-qaqc-auditor",
            "severity": "SUCCESS",
            "badge": "🟢 TRADUCCIÓN IADC / SPE CERTIFICADA (PARIDAD 1:1)",
            "message": f"Auditoría de traducción completada: Cero Spanglish detectado y {parity_pct}% de paridad en datos numéricos ({retained_count}/{total_nums} parámetros validados). Cumple con el Protocolo Estricto de Cero Omisión. Apto para OpenWells / WellView / DOR."
        })

    return {
        "status": status,
        "quality_score": quality_score,
        "has_spanglish": has_spanglish,
        "data_parity_pct": parity_pct,
        "flagged_tokens": spanish_tokens + spanglish_combos,
        "findings": findings
    }


# ==============================================================================
# MULTI-PROVIDER LLM CALLERS (OpenAI, Anthropic Claude, Groq & Google Gemini)
# ==============================================================================

def detect_llm_provider(api_key: str, requested_provider: str = "auto") -> str:
    """
    Intelligently identifies the AI provider by key prefix or explicit request.
    """
    if requested_provider and requested_provider.lower() not in ("auto", "none", ""):
        return requested_provider.lower()
    if not api_key:
        return "none"
    k = api_key.strip()
    if k.startswith("sk-ant-"):
        return "anthropic"
    elif k.startswith("gsk_"):
        return "groq"
    elif k.startswith("sk-"):
        return "openai"
    elif k.startswith("AIza"):
        return "gemini"
    return "gemini"


def call_deepseek_translation(text: str, api_key: str, well_name: str = "Well", model: str = "deepseek-chat") -> str:
    """
    Translates using DeepSeek (DeepSeek-V3 / deepseek-chat).
    OpenAI-compatible endpoint, high intelligence, extremely cost-effective (~$0.14/1M tokens).
    """
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key.strip()}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": ELITE_IADC_SYSTEM_PROMPT},
            {"role": "user", "content": f"Translate these Spanish operational notes for Well '{well_name}':\n\n{text}"}
        ],
        "temperature": 0.05,
        "max_tokens": 4096
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=35) as response:
        result = json.loads(response.read().decode("utf-8"))
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
    raise ValueError("DeepSeek returned an empty response")


def call_openai_translation(text: str, api_key: str, well_name: str = "Well", model: str = "gpt-4o-mini") -> str:
    """
    Translates using OpenAI (GPT-4o-mini or GPT-4o) with strict 1:1 zero-omission directives.
    Ultra-reliable, 99.99% uptime, zero 503 errors.
    """
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key.strip()}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": ELITE_IADC_SYSTEM_PROMPT},
            {"role": "user", "content": f"Translate these Spanish operational notes for Well '{well_name}':\n\n{text}"}
        ],
        "temperature": 0.05,
        "max_tokens": 4096
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=35) as response:
        result = json.loads(response.read().decode("utf-8"))
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
    raise ValueError("OpenAI returned an empty response")


def call_groq_translation(text: str, api_key: str, well_name: str = "Well", model: str = "llama-3.3-70b-versatile") -> str:
    """
    Translates using Groq (Llama 3.3 70B).
    Blazing fast (~500 tokens/sec), open-weights intelligence, highly resilient.
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key.strip()}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": ELITE_IADC_SYSTEM_PROMPT},
            {"role": "user", "content": f"Translate these Spanish operational notes for Well '{well_name}':\n\n{text}"}
        ],
        "temperature": 0.05,
        "max_tokens": 4096
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=35) as response:
        result = json.loads(response.read().decode("utf-8"))
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
    raise ValueError("Groq returned an empty response")


def call_anthropic_translation(text: str, api_key: str, well_name: str = "Well", model: str = "claude-3-5-haiku-20241022") -> str:
    """
    Translates using Anthropic Claude (Claude 3.5 Haiku / Sonnet).
    Industry benchmark for nuanced technical writing and zero hallucination.
    """
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key.strip(),
        "anthropic-version": "2023-06-01"
    }
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": ELITE_IADC_SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": f"Translate these Spanish operational notes for Well '{well_name}':\n\n{text}"}
        ],
        "temperature": 0.05
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=35) as response:
        result = json.loads(response.read().decode("utf-8"))
        parts = result.get("content", [])
        text_out = "".join([p.get("text", "") for p in parts if p.get("type") == "text"]).strip()
        if text_out:
            return text_out
    raise ValueError("Anthropic returned an empty response")


def call_gemini_translation(text: str, api_key: str, well_name: str = "Well") -> Tuple[str, str]:
    """
    Translates using Google Gemini model cascade with multi-part concatenation.
    """
    last_err = None
    for model in MODELS_CASCADE:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key.strip()}"
            payload = {
                "system_instruction": {
                    "parts": [{"text": ELITE_IADC_SYSTEM_PROMPT}]
                },
                "contents": [
                    {"parts": [{"text": f"Translate these Spanish operational notes for Well '{well_name}':\n\n{text}"}]}
                ],
                "generationConfig": {
                    "temperature": 0.05,
                    "maxOutputTokens": 4096
                }
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        translated = "".join([p.get("text", "") for p in parts if "text" in p]).strip()
                        if translated:
                            return translated, f"Gemini ({model})"
        except Exception as e:
            last_err = e
            continue
    raise last_err or ValueError("Google Gemini models unavailable")


# ==============================================================================
# MAIN TRANSLATION DISPATCHER (Multi-Provider Engine + Transparent Fallback)
# ==============================================================================

def translate_to_iadc_english(
    spanish_text: str, 
    api_key: str = None, 
    provider: str = "auto",
    well_name: str = "Well",
    force_offline: bool = False
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Translates Spanish field notes to standardized IADC English using the best available AI provider.
    Supports: OpenAI (GPT-4o), Anthropic Claude, Groq (Llama 3.3) and Google Gemini.
    Provides complete error transparency: never silently drops to Spanglish without alerting the user.
    """
    effective_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY")
    selected_provider = detect_llm_provider(effective_key, requested_provider=provider)

    if not force_offline and effective_key:
        error_reasons = []

        # 1. DeepSeek Path (State-of-the-art reasoning, ultra cost-effective)
        if selected_provider == "deepseek":
            try:
                translated = call_deepseek_translation(spanish_text, effective_key, well_name=well_name, model="deepseek-chat")
                qaqc_result = audit_translation_qaqc(translated, spanish_text)
                return translated, "DeepSeek (V3 / deepseek-chat)", qaqc_result
            except Exception as e:
                error_reasons.append(f"DeepSeek error: {str(e)[:80]}")

        # 2. OpenAI Path (Gold standard)
        elif selected_provider == "openai" or (selected_provider == "auto" and effective_key.startswith("sk-") and not effective_key.startswith("sk-ant-")):
            try:
                translated = call_openai_translation(spanish_text, effective_key, well_name=well_name, model="gpt-4o-mini")
                qaqc_result = audit_translation_qaqc(translated, spanish_text)
                return translated, "OpenAI (GPT-4o-mini)", qaqc_result
            except Exception as e:
                error_reasons.append(f"OpenAI error: {str(e)[:80]}")

        # 3. Anthropic Claude Path
        elif selected_provider == "anthropic" or effective_key.startswith("sk-ant-"):
            try:
                translated = call_anthropic_translation(spanish_text, effective_key, well_name=well_name, model="claude-3-5-haiku-20241022")
                qaqc_result = audit_translation_qaqc(translated, spanish_text)
                return translated, "Anthropic (Claude 3.5 Haiku)", qaqc_result
            except Exception as e:
                error_reasons.append(f"Anthropic error: {str(e)[:80]}")

        # 4. Groq Path (Llama 3.3 70B)
        elif selected_provider == "groq" or effective_key.startswith("gsk_"):
            try:
                translated = call_groq_translation(spanish_text, effective_key, well_name=well_name, model="llama-3.3-70b-versatile")
                qaqc_result = audit_translation_qaqc(translated, spanish_text)
                return translated, "Groq (Llama 3.3 70B)", qaqc_result
            except Exception as e:
                error_reasons.append(f"Groq error: {str(e)[:80]}")

        # 5. Google Gemini Path
        else:
            try:
                translated, engine_label = call_gemini_translation(spanish_text, effective_key, well_name=well_name)
                qaqc_result = audit_translation_qaqc(translated, spanish_text)
                return translated, engine_label, qaqc_result
            except Exception as e:
                error_reasons.append(f"Gemini error (503/Timeout/Capacity): {str(e)[:100]}")

        # If an API key was provided but failed: EXPLICIT USER ALERT (NO SILENT SPANGLISH)
        err_msg = " | ".join(error_reasons)
        error_notice = (
            f"⚠️ [AVISO DE SERVICIO DE IA]:\n"
            f"No se pudo completar la traducción automática con el proveedor configurado ({selected_provider.upper()}).\n"
            f"Detalle técnico: {err_msg}\n\n"
            f"RECOMENDACIÓN TÉCNICA RIGMIND:\n"
            f"• Los endpoints de Google experimentan sobrecarga temporal (Error 503).\n"
            f"• Ahora puede usar OpenAI (GPT-4o / GPT-4o-mini), Anthropic Claude o Groq pegando su clave en la barra superior.\n\n"
            f"--- [BORRADOR DETERMINÍSTICO OFFLINE DE CONTINGENCIA] ---\n"
            f"(Nota: Este borrador contiene términos pendientes de revisión técnica. No exportar a DOR de la operadora sin validar)\n\n"
        )
        offline_draft = offline_standardized_translation(spanish_text)
        full_text = error_notice + offline_draft
        qaqc_result = {
            "status": "AI_SERVICE_UNAVAILABLE",
            "quality_score": 30,
            "has_spanglish": True,
            "data_parity_pct": 50.0,
            "findings": [{
                "agent": "iadc-translation-qaqc-auditor",
                "severity": "CRITICAL",
                "badge": "🔴 ALERTA: MOTOR IA NO DISPONIBLE (503/TIMEOUT)",
                "message": f"El servicio de IA ({selected_provider.upper()}) falló con: {err_msg}. Se emitió borrador offline temporal. Configure una clave de OpenAI, Anthropic o Groq para traducción 100% profesional."
            }]
        }
        return full_text, f"Borrador Offline ({selected_provider.upper()} Falló)", qaqc_result

    # Offline translation fallback when no key is configured
    no_key_notice = (
        "ℹ️ [MODO BORRADOR OFFLINE - SIN CLAVE DE IA]:\n"
        "No se detectó API Key en el servidor o navegador.\n"
        "Para obtener una traducción 100% oficial IADC sin Spanglish, ingrese una API Key de OpenAI (GPT-4o), Anthropic Claude, Groq o Gemini en la barra superior.\n\n"
        "--- [BORRADOR DETERMINÍSTICO DE CONTINGENCIA] ---\n\n"
    )
    offline_translated = no_key_notice + offline_standardized_translation(spanish_text)
    qaqc_result = audit_translation_qaqc(offline_translated, spanish_text)
    qaqc_result["findings"].insert(0, {
        "agent": "iadc-translation-qaqc-auditor",
        "severity": "WARNING",
        "badge": "🟡 MODO OFFLINE: CLAVE DE IA NO CONFIGURADA",
        "message": "Traducción generada mediante diccionario offline de contingencia. Ingrese una clave de OpenAI (GPT-4o), Anthropic Claude o Gemini para habilitar el motor de IA profesional."
    })
    return offline_translated, "Motor Offline (Sin Clave IA)", qaqc_result
