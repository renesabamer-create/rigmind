import os
import re
import urllib.request
import json
from collections import Counter
from typing import Dict, Any, Tuple, List

from src.engine.llm_network import execute_llm_request, detect_provider
from src.engine.learning_memory import select_relevant_examples
from src.engine.text_rules import (
    ACRONYMS,
    GLOSSARY,
    extract_number_units,
    spanish_residue,
)

# ==============================================================================
# PROMPT DE TRADUCCIÓN (IADC/SPE) + glosario obligatorio
# ==============================================================================

MODELS_GEMINI = ["gemini-flash-latest", "gemini-2.5-flash"]

ELITE_IADC_SYSTEM_PROMPT = """You are a Senior Petroleum Engineer and IADC/SPE technical translator for well intervention, workover, completions and P&A daily operations reports.

MANDATORY DIRECTIVES:
1. ZERO OMISSION: translate EVERY sentence, clause, number, unit, depth, pressure, volume, time and action. Never summarize, shorten or drop an operation. If one entry has several actions, every action must appear in English.
2. OUTPUT ONLY THE TRANSLATED TEXT: no greetings, no commentary, no bullet options.
3. ZERO SPANGLISH: every Spanish word, verb and preposition must become natural petroleum engineering English. Never output "toma of alimentos", "corte of cable", "conexiones of lineas", "bajo tension", "circulo pildora".
4. STANDARD IADC ACRONYMS: POOH (Pulled Out Of Hole), RIH (Ran In Hole), M/U (Made Up), B/O (Broke Out), L/D (Laid Down), N/U (Nippled Up), N/D (Nippled Down), R/U (Rigged Up), R/D (Rigged Down), R/M (Rig Move), WOC (Waiting On Cement), HMBP (Hydro-Mechanical Bridge Plug), PJSM (Pre-Job Safety Meeting), PUW (Pick-Up Weight), SOW (Slack-Off Weight), ROTW (Rotating Weight).
5. TERMINOLOGY: use the glossary below exactly; do not invent synonyms for standardized terms.
6. PRESERVE NUMBERS AND TIMELINES EXACTLY: keep every HH:MM range, every psi, bbl, bpm, ppg, klb, ft, lb/ft, jts, %, °F and min. Do not convert units.
7. INCOMPLETE FIELDS: the Spanish text may contain markers like "[completar: SWD, velocidad]". Translate the label, keep it bracketed and readable, e.g. "[complete: SWD, speed]". Never leave Spanish words inside a bracket.
8. NEVER ADD information that is not in the Spanish text, and never remove a bracketed marker.

GLOSSARY (Spanish -> mandatory English):
""" + "\n".join(f"- {es} -> {en}" for es, en in GLOSSARY)


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

# Conceptos cuya sigla debe aparecer en inglés si el español los menciona
CONCEPT_ACRONYMS: List[Tuple[str, str]] = [
    ("POOH", r"\bpooh\b|sac(?:a|ó|ando|ar)\s+tuber|pulling"),
    ("RIH", r"\brih\b|baj(?:a|ó|ando|ar)\s+tuber|corrida\s+de\s+tuber"),
    ("HMBP", r"\bhmbp\b|bridge\s*plug"),
    ("WOC", r"\bwoc\b|fraguado"),
    ("TOC", r"\btoc\b|toque\s+de\s+cemento"),
    ("BHA", r"\bbha\b"),
    ("PCE", r"\bpce\b|lubricador"),
    ("CCL", r"\bccl\b|correlaci[oó]n"),
    ("ESP", r"\besp\b|\bbes\b|electrosumergible"),
    ("MLE", r"\bmle\b|mls\s+joints"),
    ("R/U", r"\br/u\b|\barme\b"),
    ("R/D", r"\br/d\b|desarme"),
    ("R/M", r"\br/m\b|movilizaci[oó]n"),
    ("PJSM", r"\bpjsm\b|charla|reuni[oó]n\s+preoperacional"),
    ("NPT", r"\bnpt\b|tormenta"),
]

_NOTICE_SPLIT = re.compile(r"^-{2,}\s*\[BORRADOR.*$", re.IGNORECASE | re.MULTILINE)


def _translated_body(text: str) -> str:
    """Quita el aviso en español del modo offline antes de medir la traducción."""
    m = _NOTICE_SPLIT.search(text or "")
    return (text[m.end():] if m else (text or "")).strip()


def audit_translation_qaqc(english_text: str, spanish_text: str = "") -> Dict[str, Any]:
    """
    Verificación objetiva de la traducción:
      - español residual (palabras y verbos, no solo artículos),
      - paridad de pares número+unidad (no de números sueltos),
      - siglas exigidas por el contenido del español.
    No "certifica": reporta qué pasó y qué falta.
    """
    body = _translated_body(english_text)
    residues = spanish_residue(body)

    es_pairs = extract_number_units(spanish_text)
    en_pairs = extract_number_units(body)
    en_counter = Counter(en_pairs)
    missing_pairs: List[Tuple[str, str]] = []
    for pair in es_pairs:
        if en_counter[pair] > 0:
            en_counter[pair] -= 1
        else:
            missing_pairs.append(pair)
    parity_pct = round(100.0 * (len(es_pairs) - len(missing_pairs)) / len(es_pairs), 1) if es_pairs else 100.0

    expected = [acr for acr, pat in CONCEPT_ACRONYMS if re.search(pat, spanish_text or "", re.IGNORECASE)]
    present = [acr for acr in expected if re.search(rf"(?<![A-Za-z]){re.escape(acr)}(?![A-Za-z])", body)]
    missing_acronyms = [acr for acr in expected if acr not in present]
    acronym_pct = round(100.0 * len(present) / len(expected), 1) if expected else 100.0

    findings: List[Dict[str, Any]] = []
    if residues:
        findings.append({
            "agent": "translation-qaqc", "severity": "critical",
            "badge": "🔴 ESPAÑOL RESIDUAL EN LA TRADUCCIÓN",
            "message": "Quedaron palabras o verbos en español: " + ", ".join(residues[:12]) + ".",
            "suggestion": "Vuelva a traducir con IA o corrija esas palabras a mano antes de exportar.",
        })
    if missing_pairs:
        shown = ", ".join(f"{v} {u}" for v, u in missing_pairs[:12])
        findings.append({
            "agent": "translation-qaqc", "severity": "warning",
            "badge": "🟠 DATOS NUMÉRICOS NO APARECEN EN INGLÉS",
            "message": f"{len(missing_pairs)} de {len(es_pairs)} pares número+unidad no se conservaron: {shown}.",
            "suggestion": "Verifique que ninguna presión, volumen, cota o tiempo se haya omitido.",
        })
    if missing_acronyms:
        findings.append({
            "agent": "translation-qaqc", "severity": "info",
            "badge": "🔵 SIGLAS ESTÁNDAR NO USADAS",
            "message": "El español menciona operaciones cuya sigla IADC falta en inglés: " + ", ".join(missing_acronyms) + ".",
            "suggestion": "Use " + ", ".join(missing_acronyms) + " en la narrativa inglesa.",
        })
    if not residues and not missing_pairs:
        findings.append({
            "agent": "translation-qaqc", "severity": "success",
            "badge": "🟢 TRADUCCIÓN VERIFICADA",
            "message": f"Sin español residual, {parity_pct}% de pares número+unidad conservados y "
                       f"{len(present)}/{len(expected) or 0} siglas estándar presentes.",
        })

    if residues:
        status = "REVISAR_ESPANOL"
    elif missing_pairs:
        status = "REVISAR_DATOS"
    elif missing_acronyms:
        status = "REVISAR_SIGLAS"
    else:
        status = "VERIFICADO"

    return {
        "status": status,
        "has_spanglish": bool(residues),
        "data_parity_pct": parity_pct,
        "acronym_pct": acronym_pct,
        "flagged_tokens": residues[:20],
        "missing_numbers": [f"{v} {u}" for v, u in missing_pairs[:20]],
        "missing_acronyms": missing_acronyms,
        "numbers_total": len(es_pairs),
        "findings": findings,
    }



# ==============================================================================
# MULTI-PROVIDER LLM CALLERS (OpenAI, Anthropic Claude, Groq & Google Gemini)
# ==============================================================================

def detect_llm_provider(api_key: str, requested_provider: str = "auto") -> str:
    """
    Identifica el proveedor por la clave o por elección explícita del usuario.
    Delega en `detect_provider` para no tener dos heurísticas distintas.
    """
    if requested_provider and requested_provider.lower() not in ("auto", "none", ""):
        return requested_provider.lower()
    if not api_key or not api_key.strip():
        return "none"
    return detect_provider(api_key, requested="auto")


def _translation_user_prompt(text: str, well_name: str) -> str:
    examples = select_relevant_examples(text, limit=2)
    ex_block = ""
    if examples:
        blocks = []
        for ex in examples:
            op = ex.get("operation") or "Operation"
            es = (ex.get("spanish_exemplar") or "").strip()[:300]
            en = (ex.get("english_iadc") or "").strip()[:300]
            if es and en:
                blocks.append(f"[{op}]\nES: {es}\nEN: {en}")
        if blocks:
            ex_block = (
                "USER-APPROVED REFERENCE EXAMPLES (follow this exact style and acronyms):\n"
                + "\n---\n".join(blocks)
                + "\n\n"
            )
    return f"{ex_block}Translate these Spanish operational notes for Well '{well_name}':\n\n{text}"


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
            {"role": "user", "content": _translation_user_prompt(text, well_name)}
        ],
        "temperature": 0.05,
        "max_tokens": 8192
    }
    result = execute_llm_request(url, payload, headers, timeout=40)
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
            {"role": "user", "content": _translation_user_prompt(text, well_name)}
        ],
        "temperature": 0.05,
        "max_tokens": 8192
    }
    result = execute_llm_request(url, payload, headers, timeout=40)
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
            {"role": "user", "content": _translation_user_prompt(text, well_name)}
        ],
        "temperature": 0.05,
        "max_tokens": 8192
    }
    result = execute_llm_request(url, payload, headers, timeout=40)
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
        "max_tokens": 8192,
        "system": ELITE_IADC_SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": _translation_user_prompt(text, well_name)}
        ],
        "temperature": 0.05
    }
    result = execute_llm_request(url, payload, headers, timeout=40)
    parts = result.get("content", [])
    text_out = "".join([p.get("text", "") for p in parts if p.get("type") == "text"]).strip()
    if text_out:
        return text_out
    raise ValueError("Anthropic returned an empty response")


def call_gemini_translation(text: str, api_key: str, well_name: str = "Well") -> Tuple[str, str]:
    """Gemini con dos modelos reales, error explícito por modelo y SSL del módulo de red."""
    errors: List[str] = []
    prompt = _translation_user_prompt(text, well_name)
    for model in MODELS_GEMINI:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key.strip()}"
        payload = {
            "system_instruction": {"parts": [{"text": ELITE_IADC_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.05, "maxOutputTokens": 8192},
        }
        try:
            res = execute_llm_request(url, payload, {"Content-Type": "application/json"}, timeout=60)
        except Exception as e:
            errors.append(f"{model}: {str(e)[:80]}")
            continue
        cands = res.get("candidates", [])
        if cands:
            parts = cands[0].get("content", {}).get("parts", [])
            out = "".join(p.get("text", "") for p in parts if "text" in p).strip()
            if out:
                return out, f"Gemini ({model})"
        errors.append(f"{model}: respuesta vacía")
    raise RuntimeError("Gemini no respondió — " + " | ".join(errors))


# ==============================================================================
# DISPATCHER
# ==============================================================================

PROVIDER_LABEL = {
    "deepseek": "DeepSeek (deepseek-chat)",
    "openai": "OpenAI (gpt-4o-mini)",
    "anthropic": "Anthropic (Claude 3.5 Haiku)",
    "groq": "Groq (Llama 3.3 70B)",
    "gemini": "Google Gemini (flash)",
}


def translate_to_iadc_english(
    spanish_text: str,
    api_key: str = None,
    provider: str = "auto",
    well_name: str = "Well",
    force_offline: bool = False,
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Traduce a inglés IADC. Si hay clave, usa el proveedor elegido y NUNCA
    sustituye en silencio: si falla, devuelve un borrador marcado y un
    hallazgo crítico con el error real.
    """
    effective_key = (
        api_key
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )
    selected = detect_llm_provider(effective_key, requested_provider=provider)

    if not force_offline and effective_key and selected not in ("none", "auto"):
        callers = {
            "deepseek": lambda: call_deepseek_translation(spanish_text, effective_key, well_name=well_name),
            "openai": lambda: call_openai_translation(spanish_text, effective_key, well_name=well_name),
            "anthropic": lambda: call_anthropic_translation(spanish_text, effective_key, well_name=well_name),
            "groq": lambda: call_groq_translation(spanish_text, effective_key, well_name=well_name),
        }
        try:
            if selected == "gemini":
                translated, label = call_gemini_translation(spanish_text, effective_key, well_name=well_name)
            elif selected in callers:
                translated, label = callers[selected](), PROVIDER_LABEL[selected]
            else:
                raise RuntimeError(f"Proveedor no soportado: {selected}")
            return translated, label, audit_translation_qaqc(translated, spanish_text)
        except Exception as e:
            err = str(e)[:220]
            notice = (
                f"⚠️ [IA NO DISPONIBLE — {selected.upper()}]\n"
                f"Detalle: {err}\n\n"
                f"--- [BORRADOR OFFLINE — NO USAR COMO DOR FINAL] ---\n\n"
            )
            draft = offline_standardized_translation(spanish_text)
            qaqc = audit_translation_qaqc(draft, spanish_text)
            qaqc["findings"].insert(0, {
                "agent": "translation-qaqc", "severity": "critical",
                "badge": "🔴 FALLÓ LA IA — BORRADOR OFFLINE",
                "message": f"{selected.upper()} no respondió: {err}",
                "suggestion": "Corrija la clave o el proveedor y vuelva a traducir. Este borrador mezcla inglés y español.",
            })
            qaqc["status"] = "BORRADOR_OFFLINE"
            return notice + draft, f"Borrador offline ({selected} falló)", qaqc

    # Sin clave: borrador claramente marcado
    notice = (
        "ℹ️ [SIN CLAVE DE IA — BORRADOR OFFLINE]\n"
        "Esta salida usa un diccionario de reemplazo: no es una traducción profesional.\n"
        "Configure una clave en la barra superior para traducir con IA.\n\n"
        "--- [BORRADOR — NO USAR COMO DOR FINAL] ---\n\n"
    )
    draft = offline_standardized_translation(spanish_text)
    qaqc = audit_translation_qaqc(draft, spanish_text)
    qaqc["findings"].insert(0, {
        "agent": "translation-qaqc", "severity": "warning",
        "badge": "🟠 MODO OFFLINE SIN IA",
        "message": "Traducción generada por diccionario local; el texto mezcla inglés y español.",
        "suggestion": "Ingrese una clave de IA para una traducción real.",
    })
    qaqc["status"] = "BORRADOR_OFFLINE"
    return notice + draft, "Diccionario offline (sin clave)", qaqc
