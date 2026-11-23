import os
import re
import urllib.request
import json
from typing import Dict, Any, Tuple, List

# ==============================================================================
# MASTER PETROLEUM TRANSLATION ENGINE (Offline High-Accuracy IADC Rulebook)
# ==============================================================================

# High-priority multi-word contextual patterns
CONTEXTUAL_PATTERNS: List[Tuple[str, str]] = [
    # -------------------------------------------------------------
    # 1. Rig Moves, Mobilization & Logistics
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
    (r"\brecibi[oó]\s+equipo\s+a\s+las\s+(\d{1,2}:\d{2})\s*h\s+del\s+d[ií]a\s+(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", r"Accepted rig / Handover at \1 hrs on \2-\3-\4"),
    (r"\brealiz[oó]\s+reconocimiento\s+de\s+(\d+)\s*h\s+sobre\s+la\s+hora\s+de\s+recibo\s+de\s+equipo\b", r"recognized \1 hrs credit adjustment on rig acceptance time"),
    (r"\basociado\s+a\s+la\s+actividad\s+de\b", "associated with"),
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
    # 2. Wellhead, BOP & Pressure Tests
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
    (r"dren[oó]\s+contrapozo\s+para\s+dejar\s+libre\s+las\s+v[aá]lvulas\s+de\s+la\s+secci[oó]n\s+[ab]\s+y\s+[ab]", "Drained cellar to clear Section A and B valves"),
    (r"tom[oó]\s+presiones,?\s*chp\s*=\s*(\d+)\s*psi\.?\s*thp\s*=\s*(\d+)\s*psi", r"Recorded wellhead pressures: CHP = \1 psi, THP = \2 psi"),
    (r"evidenci[oó]\s+torniller[ií]a\s+con\s+alto\s+grado\s+de\s+corrosi[oó]n", "Noted wellhead bolts with severe corrosion"),
    (r"arrib[oó]\s+personal\s+de\s+([A-Za-z0-9\s]+)", r"\1 personnel arrived on location"),
    (r"despach[oó]\s+carrotanque\s+sencillo\s+de\s+producci[oó]n\s+con\s+(.*?)\s+a\s+estaci[oó]n\s+(.*)", r"Dispatched vacuum truck w/ \1 to \2 Station"),
    (r"arrib[oó]\s+carrotanque\s+con\s+(\d+)\s*bbl\s+de\s+agua\s+industrial\s+de\s+estaci[oó]n\s+(.*)", r"Water truck arrived w/ \1 bbl industrial water from \2 Station"),
    (r"n/u\s+set\s+de\s+bop\s+([0-9\-/”\"]+)\s*([0-9kK]+)\s+as[ií]:\s*drilling\s+spool\s+(.*?)\s*\+\s*double\s+ram\s*\+\s*anular", r"N/U \1 \2 BOP stack: Drilling spool \3 + Double Ram + Annular preventer"),

    # -------------------------------------------------------------
    # 3. Tripping, Tubulars & BHA
    # -------------------------------------------------------------
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
    (r"retir[oó]\s+l[ií]nea\s+de\s+producci[oó]n", "Disconnected production flowline"),

    # -------------------------------------------------------------
    # 4. Bridge Plugs & Downhole Mechanics
    # -------------------------------------------------------------
    (r"sent[oó]\s+bridge\s+plug\s+hidromec[aá]nico\s+de\s+([0-9\-/”\"]+)\s*@\s*(\d+)\s*ft", r"Set \1 Hydro-Mechanical Bridge Plug (HMBP) @ \2 ft MD"),
    (r"realiz[oó]\s+maniobra\s+de\s+asentamiento\s+del\s+hydro\s+mechanical\s+bridge\s+plug\s+de\s+([0-9\-/”\"]+)\s*(?:cg)?\s*@\s*(\d+)\s*ft", r"Set \1 Hydro-Mechanical Bridge Plug (HMBP) @ \2 ft MD"),
    (r"lanz[oó]\s+esfera\s+de\s+asentamiento\s+de\s+([0-9\./”\"]+)\s+y\s+dej[oó]\s+gravitar", r"Dropped \1 setting ball and allowed to gravitate"),
    (r"lanz[oó]\s+esfera\s+de\s+([0-9\./”\"]+)", r"Dropped \1 setting ball"),
    (r"cort[oó]\s+pin\s+a\s*(\d+)\s*psi", r"sheared ball seat @ \1 psi"),
    (r"observ[oó]\s+ca[ií]da\s+s[uú]bita\s+de\s+la\s+presi[oó]n\s+a\s+0\s+psi", "observed sudden pressure drop to 0 psi"),
    (r"verific[oó]\s+anclaje\s+con\s+(\d+)\s*klb\s+de\s+overpull(?:\s*\((.*?)\))?", r"confirmed anchor w/ \1 klb overpull (\2)"),
    (r"baj[oó]\s+sarta\s+y\s+aplic[oó]\s+peso\s+sobre\s+el\s+hmbp\s+de\s+(\d+(?:\.\d+)?)\s*klb", r"slacked off \1 klb weight on HMBP"),
    (r"liber[oó]\s+(?:del\s+)?hmbp\s+con\s+(\d+)\s+vueltas\s+a\s+la\s+derecha", r"released from HMBP w/ \1 RH turns"),
    (r"prob[oó]\s+integridad\s+del\s+hmbp\s+([0-9\-/”\"]+)\s+con\s+(\d+)\s*psi\s*x\s*(\d+)\s*min(?:utos)?", r"pressure tested \1 HMBP to \2 psi x \3 min (OK)"),

    # -------------------------------------------------------------
    # 5. Cementing & P&A
    # -------------------------------------------------------------
    (r"mezcl[oó]\s+cemento\s+y\s+realiz[oó]\s+tap[oó]n\s+de\s+fondo\s+de\s+(\d+)\s*ft\s+a\s+(\d+)\s*ft(?:,\s*(\d+)\s*ft\s+de\s+espesor)?", r"Mixed and spotted balanced bottom cement plug from \1 ft to \2 ft MD (\3 ft thickness)"),
    (r"balance[oó]\s+tap[oó]n\s+de\s+cemento\s+de\s+fondo", "Spotted balanced bottom cement plug"),
    (r"inici[oó]\s+tiempo\s+de\s+woc", "Commenced WOC"),
    (r"tiempo\s+de\s+woc\s*\((.*?)\)", r"Waiting on Cement (WOC) (\1)"),
    (r"revers[oó]\s+(\d+)\s*bbl\s+hasta\s+retorno\s+limpio", r"reverse circulated \1 bbl to clean returns"),
    (r"verific[oó]\s+toc\s+con\s+(\d+)\s*klb\s+a\s+(\d+(?:\.\d+)?)\s*ft", r"Tagged TOC w/ \1 klb weight @ \2 ft MD (OK)"),
    (r"recogi[oó]\s+(\d+)\s+testigos", r"Caught \1 surface witness samples"),
    (r"p[ií]ldora\s+viscosa\s+de\s+(\d+)\s*bbl", r"\1 bbl high-viscosity xanthan gum pill"),
    (r"bombe[oó]\s+fluido\s+inhibido\s+de\s+(\d+)\s*ft\s+a\s+(\d+)\s*ft", r"pumped corrosion-inhibited completion fluid from \1 ft to \2 ft MD"),

    # -------------------------------------------------------------
    # 6. Artificial Lift / ESP
    # -------------------------------------------------------------
    (r"desacople\s+de\s+sarta\s+esp", "Decoupled ESP downhole assembly"),
    (r"tom[oó]\s+medidas\s+el[eé]ctricas\s+antes\s+de\s+desacople\s+esp:", "Recorded electrical measurements prior to ESP decouple:"),
    (r"balanceado\s+con\s+falla\s+a\s+tierra", "balanced with ground fault to earth"),
    (r"dictamen:\s*falla\s+el[eé]ctrica\s+en\s+motor", "Diagnosis: electrical insulation breakdown in motor"),
    (r"retir[oó]\s+overcoupling\s+y\s+(\d+)\s+superbandas\s+por\s+junta", r"removed overcoupling & \1 superbands per joint"),
    (r"se\s+recuperaron\s+(\d+)\s*ft\s+de\s+cable\s+de\s+potencia", r"recovered \1 ft of ESP power cable"),

    # -------------------------------------------------------------
    # 7. HSE & Rig Operations
    # -------------------------------------------------------------
    (r"realiz[oó]\s+reuni[oó]n\s+de\s+seguridad\s+y\s+preoperacional\s+con\s+todo\s+el\s+personal", "Conducted pre-job safety and operations meeting w/ rig crew"),
    (r"charla\s+preoperacional\s+para\s+", "Pre-job safety meeting prior to "),
    (r"retom[oó]\s+charla\s+de\s+seguridad\s+antes\s+de\s+", "Resumed safety meeting prior to "),
    (r"divulg[oó]\s+plan\s+de\s+trabajo,?\s*defini[oó]\s+roles\s+y\s+responsabilidades", "reviewed work plan, assigned roles and responsibilities"),
    (r"analiz[oó]\s+riesgos\s+y\s+peligros\s+asociados", "assessed associated operational hazards and mitigation"),
    (r"personal\s+tomando\s+alimentos\s*\(almuerzo\)", "Crew meal break (Lunch)"),
    (r"personal\s+tomando\s+alimentos", "Crew meal break"),
    (r"personal\s+tomando\s+lonche", "Crew meal break"),
    (r"suspendi[oó]\s+operaciones\s+por\s+fuertes\s+lluvias\s+y\s+alerta\s+de\s+nivel\s+de\s+tormenta\s+([ivxIVX]+)", r"Operations suspended due to severe rainfall and Level \1 electrical storm"),
    (r"suspendi[oó]\s+operaciones\s+por\s+tormenta\s+el[eé]ctrica\s+(?:nivel\s+)?([ivxIVX0-9\-]+)", r"Operations suspended due to Level \1 electrical storm"),
    (r"npt\s+clima:\s*operaciones\s+suspendidas\s+por\s+tormenta\s+([ivxIVX]+)", r"NPT Weather: Operations suspended due to Level \1 electrical storm"),
    (r"parada\s+de\s+seguridad:\s*", "Safety stand-down: "),
    (r"ubic[oó]\s+subestructura\s+de\s+trabajo,?\s*rampa\s+y\s+planchada", "Spotted and leveled rig substructure, catwalk, and pipe racks")
]

# Comprehensive Phrase-Level & Word-Level Oilfield Lexicon
WORD_REPLACEMENTS: List[Tuple[str, str]] = [
    # Multi-word idioms & phrases
    (r"\bmovilizaci[oó]n\s+lump\s+sum\b", "lump sum rig mobilization"),
    (r"\bmoviliz[oó]\s+lump\s+sum\b", "mobilized lump sum"),
    (r"\bmovilizaci[oó]n\s+de\s+(?:equipo|taladro|torre)\b", "rig mobilization"),
    (r"\bmovilizaci[oó]n\b", "rig mobilization"),
    (r"\bmoviliz[oó]\s+(?:equipo|taladro|torre)\b", "mobilized rig"),
    (r"\bmoviliz[oó]\b", "mobilized"),
    (r"\bdesarme\s+de\s+(?:equipo|taladro|torre)\b", "rig down (R/D)"),
    (r"\barme\s+de\s+(?:equipo|taladro|torre)\b", "rig up (R/U)"),
    (r"\bdesarme\b", "rig down (R/D)"),
    (r"\barme\b", "rig up (R/U)"),
    (r"\btraslado\s+de\s+cargas\b", "loads transport"),
    (r"\bcargas?\s+movilizadas?\b", "mobilized loads"),
    (r"\bcargas?\s+transportadas?\b", "transported loads"),
    (r"\bcargas?\b", "loads"),
    (r"\bmismo\s+pad\b", "same pad"),
    (r"\bmisma\s+locaci[oó]n\b", "same location"),
    (r"\bdentro\s+del\s+mismo\s+pad\b", "within the same pad"),
    (r"\bdentro\s+del\b", "within the"),
    (r"\bdentro\s+de\b", "within"),
    (r"\bentro\s+de\b", "within"),
    (r"\bequipo\s+de\s+workover\b", "workover rig"),
    (r"\bequipo\s+de\s+reacondicionamiento\b", "workover rig"),
    (r"\bequipo\s+de\s+perforaci[oó]n\b", "drilling rig"),
    (r"\btaladro\s+de\s+workover\b", "workover rig"),
    (r"\btaladro\b", "rig"),
    (r"\btorre\b", "rig"),
    (r"\bequipo\b", "rig"),
    (r"\bcami[oó]n\s+gr[uú]a\b", "crane truck"),
    (r"\bgr[uú]a\b", "crane"),
    (r"\bcarrotanque\b", "tanker truck"),
    (r"\bcama\s+baja\b", "lowboy trailer"),
    (r"\btractomula\b", "transport truck"),

    # Well locations & connectors
    (r"\bdesde\s+el\s+pozo\b", "from well"),
    (r"\bdesde\s+pozo\b", "from well"),
    (r"\bhacia\s+el\s+pozo\b", "to well"),
    (r"\bhacia\s+pozo\b", "to well"),
    (r"\bal\s+pozo\b", "to well"),
    (r"\ba\s+pozo\b", "to well"),
    (r"\bdel\s+pozo\b", "of well"),
    (r"\bde\s+locaci[oó]n\b", "from location"),
    (r"\bhacia\s+la\s+locaci[oó]n\b", "to location"),
    (r"\bhacia\s+locaci[oó]n\b", "to location"),
    (r"\ba\s+la\s+locaci[oó]n\b", "to location"),
    (r"\ba\s+locaci[oó]n\b", "to location"),
    (r"\blocaci[oó]n\b", "location"),
    (r"\bpozo\b", "well"),

    # Field Operations & Actions
    (r"\brealiz[oó]\s+reuni[oó]n\s+de\s+seguridad\b", "Conducted safety meeting"),
    (r"\bcharla\s+de\s+seguridad\b", "safety meeting"),
    (r"\breuni[oó]n\s+de\s+seguridad\b", "safety meeting"),
    (r"\bcharla\s+preoperacional\b", "pre-job safety meeting"),
    (r"\breuni[oó]n\s+preoperacional\b", "pre-job meeting"),
    (r"\brealiz[oó]\b", "conducted"),
    (r"\bse\s+realiz[oó]\b", "conducted"),
    (r"\binici[oó]\b", "commenced"),
    (r"\bse\s+inici[oó]\b", "commenced"),
    (r"\binicio\s+de\b", "commenced"),
    (r"\bfinaliz[oó]\b", "completed"),
    (r"\bse\s+finaliz[oó]\b", "completed"),
    (r"\bcontinu[oó]\b", "continued"),
    (r"\bse\s+continu[oó]\b", "continued"),
    (r"\bprocedi[oó]\s+a\b", "proceeded to"),
    (r"\bobserv[oó]\b", "observed"),
    (r"\bse\s+observ[oó]\b", "observed"),
    (r"\bverific[oó]\b", "verified"),
    (r"\bse\s+verific[oó]\b", "verified"),
    (r"\bubic[oó]\b", "spotted"),
    (r"\barm[oó]\b", "rigged up"),
    (r"\bdesarm[oó]\b", "rigged down"),
    (r"\binstal[oó]\b", "installed"),
    (r"\bretir[oó]\b", "retrieved"),
    (r"\bbombe[oó]\b", "pumped"),
    (r"\bse\s+bombe[oó]\b", "pumped"),
    (r"\bcircul[oó]\b", "circulated"),
    (r"\bdesplaz[oó]\b", "displaced"),
    (r"\bpresuriz[oó]\b", "pressured up"),
    (r"\bconect[oó]\b", "connected"),
    (r"\bdesconect[oó]\b", "disconnected"),
    (r"\bllen[oó]\b", "filled"),
    (r"\bsac[oó]\b", "pulled"),
    (r"\bbaj[oó]\b", "ran in"),

    # Fluids & Cement
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
    (r"\bevidenci[oó]\s+succi[oó]n\s+en\s+backflow\b", "evidenced U-tube suction in backflow"),

    # Tubulars & Strings
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

    # Wellhead & Pressure Tests
    (r"\bprueba\s+de\s+bop\s+anular\b", "Annular BOP pressure test"),
    (r"\bprueba\s+de\s+bop\b", "BOP pressure test"),
    (r"\bprueba\s+de\s+hermeticidad\b", "leak-off / pressure integrity test"),
    (r"\bprueba\s+de\s+integridad\b", "pressure integrity test"),
    (r"\bprueba\s+de\s+presi[oó]n\b", "pressure test"),
    (r"\bprueba\s+de\b", "pressure test of"),
    (r"\bpruebas\b", "pressure tests"),
    (r"\bprueba\b", "pressure test"),
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

    # Technical Acronyms & Units
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
    (r"(?<!\()\bok\b(?!\))", "(OK)"),

    # Syntactic Connectors & Prepositions
    (r"\bdesde\b", "from"),
    (r"\bhacia\b", "to"),
    (r"\bhasta\b", "to"),
    (r"\bcon\b", "w/"),
    (r"\bsin\b", "w/o"),
    (r"\bpara\b", "to"),
    (r"\bpor\b", "due to"),
    (r"\bal\b", "at"),
    (r"\bdel\b", "of"),
    (r"\bde\b", "of"),
    (r"\ba\b", "to"),
    (r"\by\b", "and")
]


def offline_standardized_translation(text: str) -> str:
    """
    Enhanced deterministic translation engine that transforms entire Spanish field logs
    into fluent, standardized IADC English narratives with technical oilfield acronyms.
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

        # Clean double prepositions like 'from to' or 'of to'
        t_line = re.sub(r"\bof\s+of\b", "of", t_line, flags=re.IGNORECASE)
        t_line = re.sub(r"\bto\s+to\b", "to", t_line, flags=re.IGNORECASE)
        t_line = re.sub(r"\bfrom\s+from\b", "from", t_line, flags=re.IGNORECASE)
        t_line = re.sub(r"\bw/\s+w/\b", "w/", t_line, flags=re.IGNORECASE)
        t_line = re.sub(r"\bof\s+at\b", "at", t_line, flags=re.IGNORECASE)
        t_line = re.sub(r"\bto\s+at\b", "to", t_line, flags=re.IGNORECASE)

        # Capitalize first letter of line
        if len(t_line) > 1:
            t_line = t_line[0].upper() + t_line[1:]

        translated_lines.append(t_line)

    return "\n".join(translated_lines)


def translate_to_iadc_english(spanish_text: str, api_key: str = None, well_name: str = "Well") -> Tuple[str, str]:
    """
    Translates Spanish field notes to standardized IADC English.
    Tries Gemini API first (if API key is present); falls back to the enhanced offline engine.
    Returns:
        (translated_text, engine_source)
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")

    if api_key:
        models = ["gemini-2.0-flash", "gemini-1.5-flash"]
        for model in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                system_instruction = (
                    "You are an elite petroleum engineer and IADC technical translator. "
                    "Translate the following Spanish well intervention notes into 100% standard, concise, professional oilfield English. "
                    "Enforce standard industry acronyms (POOH, RIH, M/U, L/D, N/U, N/D, HMBP, WOC, PUW, SOW, ROTW, R/D, R/M, R/U). "
                    "Translate all Spanish words, prepositions, numbers, and rig descriptions into English. "
                    "Never leave Spanish words or Spanglish. Return only the final standardized English narrative."
                )
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": f"{system_instruction}\n\n[Spanish Notes]:\n{spanish_text}"}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 2048
                    }
                }
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=12) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    candidates = result.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip(), f"Gemini ({model})"
            except Exception:
                continue

    # Offline translation fallback
    return offline_standardized_translation(spanish_text), "Motor Especializado Offline IADC"
