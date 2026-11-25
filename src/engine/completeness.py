"""
Motor de COMPLETITUD por tipo de operación.

Para cada maniobra detectada en el reporte (POOH, RIH, asentamiento de HMBP,
tapón de cemento, prueba de BOP, circulación, wireline, rig move, ESP, NPT,
charla de seguridad, wellhead) define exactamente qué parámetros exige un
revisor de operaciones y devuelve:

  - qué está presente (con el texto detectado como evidencia),
  - qué falta, con prioridad y ejemplo de cómo escribirlo,
  - un puntaje de completitud global y por operación.

No reescribe el texto: eso lo decide el auditor (solo agrega marcadores
'[completar: ...]' en los eventos que sí tienen campos faltantes).
"""

import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Definición de operaciones
# ---------------------------------------------------------------------------
# field:  key, label (para el usuario), short (para el marcador),
#         priority ("requerido" | "recomendado"),
#         hint (ejemplo de cómo se escribe), standard (norma o práctica),
#         any / all (regex)  ->  presente si coincide alguna / todas
# ---------------------------------------------------------------------------

OPS: Dict[str, Dict[str, Any]] = {
    "POOH": {
        "label": "Sacada de tubería (POOH)",
        "detect": [r"\bpooh\b", r"sacando\s+tuber", r"se\s+retiran?\s+\d+\s+juntas",
                   r"quebrando\s+en\s+sencillos", r"\bpulling\b", r"sacó\s+tuber"],
        "fields": [
            {"key": "cotas", "label": "Cotas desde/hasta (ft)", "short": "cotas", "priority": "requerido",
             "any": [r"\d{3,5}(?:\.\d+)?\s*ft\s*(?:a|hasta|-)\s*\d{3,5}",
                     r"desde\s+\d{3,5}(?:\.\d+)?\s*ft\s+hasta\s+\d{3,5}"],
             "hint": "desde 5720 ft hasta 4944 ft", "standard": "IADC DOR"},
            {"key": "tally", "label": "Fracción de juntas (x/y jtas)", "short": "tally", "priority": "requerido",
             "any": [r"\d+\s*/\s*\d+\s*(?:jtas?|juntas?|jts?)"],
             "hint": "25/150 jtas", "standard": "Tally / IADC"},
            {"key": "avance", "label": "Avance %", "short": "avance", "priority": "requerido",
             "any": [r"avance\s*[:=]?\s*\d+(?:\.\d+)?\s*%"],
             "hint": "avance: 16.7%", "standard": "Tally / IADC"},
            {"key": "tubular", "label": "Especificación del tubular (OD, lb/ft, grado, rosca)", "short": "tubular",
             "priority": "requerido", "scope": "report",
             "all": [r"(?:tbg|tuber[ií]a|dp|drill\s*pipe|varilla|sarta)[^.\n]{0,25}\d(?:-\d/\d)?\"?",
                     r"\d+(?:\.\d+)?\s*(?:lb/ft|#)"],
             "hint": 'TBG 3-1/2" 9.3 lb/ft N-80 EUE', "standard": "API Spec 5CT"},
            {"key": "pesos", "label": "Pesos SWU/PUW y SWD/SOW (klb)", "short": "SWU/SWD", "priority": "requerido",
             "all": [r"\b(?:swu|puw|peso\s+subiendo)\b", r"\b(?:swd|sow|peso\s+bajando)\b"],
             "hint": "SWU 45 klb / SWD 39.5 klb", "standard": "Práctica de sarta"},
            {"key": "velocidad", "label": "Velocidad (jts/h o ft/h)", "short": "velocidad", "priority": "recomendado",
             "any": [r"\d+(?:\.\d+)?\s*(?:jtas?/h|jts?/h|jtas?/hr|ft/h|ft/hr)"],
             "hint": "10 jtas/h = 313 ft/h", "standard": "IADC DOR"},
            {"key": "modo", "label": "Modo de maniobra (sencillos/dobles)", "short": "modo", "priority": "recomendado", "scope": "report",
             "any": [r"\b(?:sencillos|dobles|stands|paradas|rack|peine)\b"],
             "hint": "quebrando en sencillos a rack", "standard": "IADC DOR"},
            {"key": "llenado", "label": "Llenado de pozo / trip tank", "short": "trip tank", "priority": "recomendado",
             "any": [r"tuber[ií]a\s+llena", r"tuber[ií]a\s+seca", r"trip\s*tank", r"tanque\s+de\s+viaje",
                     r"pozo\s+lleno", r"llenando\s+pozo"],
             "hint": "tubería llena, reposición en trip tank 12 bbl", "standard": "API RP 59"},
        ],
    },
    "RIH": {
        "label": "Corrida de tubería (RIH)",
        "detect": [r"\brih\b", r"bajando\s+tuber", r"bajar\s+tuber", r"corrida\s+de\s+tuber"],
        "fields": [
            {"key": "cotas", "label": "Cotas desde/hasta (ft)", "short": "cotas", "priority": "requerido",
             "any": [r"desde\s+(?:superficie|\d{3,5}(?:\.\d+)?)\s*ft\s+hasta\s+\d{3,5}",
                     r"\d{3,5}(?:\.\d+)?\s*ft\s*(?:a|hasta|-)\s*\d{3,5}"],
             "hint": "desde superficie hasta 5720 ft", "standard": "IADC DOR"},
            {"key": "tally", "label": "Fracción de juntas (x/y jtas)", "short": "tally", "priority": "requerido",
             "any": [r"\d+\s*/\s*\d+\s*(?:jtas?|juntas?|jts?)"],
             "hint": "26/150 jtas", "standard": "Tally / IADC"},
            {"key": "tubular", "label": "Especificación del tubular", "short": "tubular", "priority": "requerido", "scope": "report",
             "all": [r"(?:tbg|tuber[ií]a|dp|drill\s*pipe)[^.\n]{0,25}\d(?:-\d/\d)?\"?",
                     r"\d+(?:\.\d+)?\s*(?:lb/ft|#)"],
             "hint": 'TBG 3-1/2" 9.3 lb/ft N-80 EUE', "standard": "API Spec 5CT"},
            {"key": "pesos", "label": "Pesos SWU/PUW y SWD/SOW", "short": "SWU/SWD", "priority": "requerido",
             "all": [r"\b(?:swu|puw|peso\s+subiendo)\b", r"\b(?:swd|sow|peso\s+bajando)\b"],
             "hint": "SWU 45 klb / SWD 39.5 klb", "standard": "Práctica de sarta"},
            {"key": "velocidad", "label": "Velocidad (jts/h o ft/h)", "short": "velocidad", "priority": "recomendado",
             "any": [r"\d+(?:\.\d+)?\s*(?:jtas?/h|jts?/h|ft/h|ft/hr)"],
             "hint": "10 jtas/h", "standard": "IADC DOR"},
            {"key": "bha", "label": "BHA / objetivo de la corrida", "short": "BHA/objetivo", "priority": "recomendado",
             "any": [r"\bbha\b", r"pesca", r"completamiento", r"limpieza", r"registro"],
             "hint": "BHA de limpieza con molino", "standard": "IADC DOR"},
        ],
    },
    "HMBP": {
        "label": "Tapón mecánico (HMBP)",
        "detect": [r"\bhmbp\b", r"bridge\s*plug", r"tap[oó]n\s+mec[aá]nico"],
        "variant_detect": [
            (r"sent[oó]|asent[oó]|coloc[oó]|presuriz[oó]|cort[oó]\s+pin|anclaje", "set"),
            (r"liber[oó]|prob[oó]|prueba\s+de\s+integridad", "release"),
        ],
        "variants": {
            "set": ["cota", "presion", "anclaje", "peso", "liberacion", "prueba", "carta", "fluido"],
            "release": ["liberacion", "prueba", "carta"],
        },
        "fields": [
            {"key": "cota", "label": "Cota de asentamiento (ft)", "short": "cota", "priority": "requerido",
             "any": [r"@\s*\d{3,5}\s*ft", r"\d{3,5}(?:\.\d+)?\s*ft\s*(?:md)?"],
             "hint": "@ 5720 ft MD", "standard": "IADC DOR"},
            {"key": "presion", "label": "Presión de asentamiento / corte de pin (psi)", "short": "presión asent.", "priority": "requerido",
             "any": [r"(?:presuriz|asent|sent)[^.\n]{0,60}\d{3,4}\s*psi", r"cort[oó]\s+pin[^.\n]{0,40}\d{3,4}\s*psi"],
             "hint": "cortó pin a 3200 psi con caída a 0 psi", "standard": "Procedimiento del fabricante"},
            {"key": "anclaje", "label": "Prueba de anclaje (klb x min)", "short": "anclaje", "priority": "requerido",
             "any": [r"(?:sobretensi[oó]n|overpull|anclaje)[^.\n]{0,60}\d+(?:\.\d+)?\s*klb[^.\n]{0,40}(?:\d+\s*min|x\s*\d+)"],
             "hint": "verificó anclaje con 40 klb x 5 min", "standard": "NORSOK D-010 (verificación de barrera)"},
            {"key": "peso", "label": "Peso aplicado sobre el tapón (klb)", "short": "peso en tapón", "priority": "recomendado",
             "any": [r"(?:aplic[oó]|baj[oó])[^.\n]{0,40}\d+(?:\.\d+)?\s*klb"],
             "hint": "aplicó 7 klb sobre el HMBP", "standard": "Procedimiento del fabricante"},
            {"key": "liberacion", "label": "Liberación (vueltas a la derecha)", "short": "liberación", "priority": "requerido",
             "any": [r"vueltas?\s+a\s+la\s+derecha", r"\b\d+\s+vueltas\b[^.\n]{0,30}hmbp"],
             "hint": "liberó con 10 vueltas a la derecha bajo 48 klb", "standard": "Procedimiento del fabricante"},
            {"key": "prueba", "label": "Prueba de integridad (psi x min)", "short": "prueba integridad", "priority": "requerido",
             "any": [r"(?:prueba|prob[oó])[^.\n]{0,60}\d{3,4}\s*psi[^.\n]{0,30}\d+\s*min"],
             "hint": "probó integridad con 500 psi x 15 min", "standard": "API 53 / NORSOK D-010"},
            {"key": "carta", "label": "Registro en carta Barton", "short": "carta Barton", "priority": "recomendado",
             "any": [r"carta\s+(?:bart[oó]n|manom[eé]trica)"],
             "hint": "registrado en carta Barton No. 214", "standard": "Práctica de integridad"},
            {"key": "fluido", "label": "Fluido de prueba y volumen", "short": "fluido de prueba", "priority": "recomendado",
             "any": [r"(?:agua\s+industrial|salmuera)[^.\n]{0,40}\d+\s*bbl"],
             "hint": "10 bbl de agua industrial", "standard": "Práctica de integridad"},
        ],
    },
    "CEMENT_PLUG": {
        "label": "Tapón de cemento",
        "detect": [r"tap[oó]n\s+de\s+(?:fondo|cemento)[^.]{0,60}(?:ft|bbl|ppg|lechada)", r"lechada[^.]{0,40}(?:bbl|ppg)", r"cement\s+plug"],
        "fields": [
            {"key": "intervalo", "label": "Intervalo del tapón (ft a ft)", "short": "intervalo", "priority": "requerido",
             "any": [r"de\s+\d{3,5}(?:\.\d+)?\s*ft\s+a\s+\d{3,5}", r"desde\s+\d{3,5}\s*ft\s+hasta\s+\d{3,5}"],
             "hint": "de 5720 ft a 5331 ft", "standard": "NORSOK D-010 / API RP 96"},
            {"key": "espesor", "label": "Espesor calculado (ft)", "short": "espesor", "priority": "requerido",
             "any": [r"\d+\s*ft\s*(?:de\s+)?espesor"],
             "hint": "389 ft de espesor", "standard": "NORSOK D-010 / API RP 96"},
            {"key": "lechada", "label": "Volumen y densidad de lechada (bbl / ppg)", "short": "lechada bbl/ppg",
             "priority": "requerido",
             "all": [r"\d+(?:\.\d+)?\s*bbl[^.\n]{0,40}(?:lechada|cemento|slurry)",
                     r"\d+(?:\.\d+)?\s*ppg"],
             "hint": "16 bbl de lechada Clase G a 15.8 ppg", "standard": "API Spec 10A"},
            {"key": "clase", "label": "Clase de cemento", "short": "clase", "priority": "recomendado",
             "any": [r"clase\s+[gh]", r"class\s+[gh]"],
             "hint": "Clase G", "standard": "API Spec 10A"},
            {"key": "preflujo", "label": "Preflujo (bbl)", "short": "preflujo", "priority": "recomendado",
             "any": [r"preflujo[^.\n]{0,30}\d+\s*bbl", r"\d+\s*bbl\s+de\s+preflujo"],
             "hint": "5 bbl de preflujo de agua fresca", "standard": "Práctica de cementación"},
            {"key": "desplazamiento", "label": "Desplazamiento (bbl)", "short": "desplazamiento", "priority": "requerido",
             "any": [r"desplaz[oó][^.\n]{0,40}\d+\s*bbl", r"desplazamiento[^.\n]{0,30}\d+\s*bbl"],
             "hint": "desplazó con 36 bbl de agua", "standard": "Balance de tapón"},
            {"key": "tasa", "label": "Tasa y presión de bombeo (bpm / psi)", "short": "bpm/psi", "priority": "requerido",
             "all": [r"\d+(?:\.\d+)?\s*bpm", r"\d{2,4}\s*psi"],
             "hint": "a 3 bpm con 80 psi", "standard": "Práctica de cementación"},
            {"key": "woc", "label": "Tiempo de WOC (h)", "short": "WOC", "priority": "requerido", "scope": "report",
             "any": [r"woc[^.\n]{0,20}\d+(?:\.\d+)?", r"fraguado[^.\n]{0,20}\d+"],
             "hint": "WOC 10 h", "standard": "API RP 96"},
            {"key": "toc", "label": "Verificación de TOC con peso (klb)", "short": "TOC klb", "priority": "recomendado", "scope": "report",
             "any": [r"toc[^.\n]{0,40}\d+(?:\.\d+)?\s*klb", r"toque[^.\n]{0,40}\d+(?:\.\d+)?\s*klb"],
             "hint": "tagged TOC con 10 klb", "standard": "NORSOK D-010"},
            {"key": "testigos", "label": "Testigos de superficie", "short": "testigos", "priority": "recomendado",
             "any": [r"testigos?"],
             "hint": "recogió 3 testigos", "standard": "Práctica de cementación"},
            {"key": "retornos", "label": "Retornos / succión en backflow", "short": "retornos", "priority": "recomendado",
             "any": [r"retorno", r"backflow", r"succi[oó]n"],
             "hint": "evidenció succión en backflow", "standard": "Práctica de cementación"},
        ],
    },
    "BOP_TEST": {
        "label": "Prueba de BOP / preventoras",
        "detect": [r"prueba\s+de\s+(?:bop|anular|preventor|pipe\s*rams?|blind\s*rams?|shear\s*rams?)",
                   r"preventoras?", r"bop\s+stack", r"\bchoke\s+manifold\b"],
        "fields": [
            {"key": "componente", "label": "Componente probado (anular/arietes/blind/manifold)", "short": "componente",
             "priority": "requerido",
             "any": [r"anular", r"pipe\s*rams?", r"blind\s*rams?", r"shear\s*rams?", r"choke\s*manifold", r"arietes?"],
             "hint": "anular + pipe rams + blind rams + choke manifold", "standard": "API 53"},
            {"key": "baja", "label": "Prueba en baja (psi x min)", "short": "prueba baja", "priority": "requerido",
             "any": [r"en\s+baja[^.\n]{0,30}\d{2,4}\s*psi[^.\n]{0,20}\d+\s*min"],
             "hint": "en baja con 300 psi x 5 min", "standard": "API 53 (250-350 psi, 5 min)"},
            {"key": "alta", "label": "Prueba en alta (psi x min)", "short": "prueba alta", "priority": "requerido",
             "any": [r"en\s+alta[^.\n]{0,30}\d{3,5}\s*psi[^.\n]{0,20}\d+\s*min"],
             "hint": "en alta con 5000 psi x 10 min", "standard": "API 53 (RWP o MASP)"},
            {"key": "aceptacion", "label": "Criterio de aceptación (0 psi de caída / ok)", "short": "aceptación",
             "priority": "requerido",
             "any": [r"0\s*psi\s+de\s+ca[ií]da", r"sin\s+ca[ií]da", r"carta", r"\bok\b"],
             "hint": "'0 psi de caída en 10 min'", "standard": "API 53"},
            {"key": "especificacion", "label": "Especificación del BOP (diámetro x presión)", "short": "spec BOP",
             "priority": "recomendado",
             "any": [r"\d(?:-\d/\d)?\"?\s*(?:x|×)\s*\d+\s*[kK]"],
             "hint": '7-1/16" 5K', "standard": "API 16A"},
            {"key": "carta", "label": "Carta de registro", "short": "carta", "priority": "recomendado",
             "any": [r"carta\s+(?:bart[oó]n|manom[eé]trica|registradora)", r"registro\s+de\s+presi[oó]n"],
             "hint": "carta manométrica circular", "standard": "API 53"},
        ],
    },
    "CIRCULATION": {
        "label": "Circulación / bombeo",
        "detect": [r"circul[oó]", r"circulaci[oó]n", r"p[ií]ldora", r"desplaz[oó]", r"revers[oó]", r"retorno\s+limpio"],
        "fields": [
            {"key": "fluido", "label": "Fluido (agua/salmuera/lodo/píldora)", "short": "fluido", "priority": "requerido",
             "any": [r"agua\s+(?:industrial|fresca)", r"salmuera", r"lodo", r"surfactante", r"x[aá]ntica", r"p[ií]ldora"],
             "hint": "agua industrial / salmuera / píldora de surfactante", "standard": "Práctica de fluidos"},
            {"key": "volumen", "label": "Volumen (bbl)", "short": "volumen", "priority": "requerido",
             "any": [r"\d+(?:\.\d+)?\s*bbl"],
             "hint": "60 bbl", "standard": "IADC DOR"},
            {"key": "tasa", "label": "Tasa de bombeo (bpm)", "short": "bpm", "priority": "requerido",
             "any": [r"\d+(?:\.\d+)?\s*bpm"],
             "hint": "3 bpm", "standard": "IADC DOR"},
            {"key": "presion", "label": "Presión de bombeo (psi)", "short": "psi", "priority": "recomendado",
             "any": [r"\d{2,4}\s*psi"],
             "hint": "200 psi", "standard": "IADC DOR"},
            {"key": "retornos", "label": "Retornos / pérdidas / catch tank", "short": "retornos", "priority": "recomendado",
             "any": [r"retorno", r"catch\s*tank", r"p[eé]rdida", r"ganancia"],
             "hint": "retorno a catch tank, pérdidas 2 bbl", "standard": "Control de pozo"},
            {"key": "direccion", "label": "Dirección (directa/reversa)", "short": "dirección", "priority": "recomendado",
             "any": [r"en\s+directa", r"en\s+reversa"],
             "hint": "circulación en reversa", "standard": "IADC DOR"},
        ],
    },
    "WIRELINE": {
        "label": "Wireline / Slickline / Cañoneo",
        "detect": [r"wireline", r"slickline", r"ca[ñn][oó]n", r"dispar[oó]", r"\bccl\b", r"lubricador",
                   r"registro\s+(?:cbl|vdl|plt|usit)", r"l[ií]nea\s+de\s+acero"],
        "fields": [
            {"key": "herramienta", "label": "Herramienta / cañón utilizado", "short": "herramienta", "priority": "requerido",
             "any": [r"ca[ñn][oó]n[^.\n]{0,30}\d", r"herramienta[^.\n]{0,30}", r"registro[^.\n]{0,30}"],
             "hint": 'cañón de casing 4-1/2" 6 spf', "standard": "IADC DOR"},
            {"key": "cota", "label": "Profundidad de la operación (ft)", "short": "cota", "priority": "requerido",
             "any": [r"\d{3,5}(?:\.\d+)?\s*ft"],
             "hint": "a 5720 ft", "standard": "IADC DOR"},
            {"key": "pce", "label": "Prueba de PCE / lubricador (psi x min)", "short": "prueba PCE", "priority": "requerido",
             "any": [r"(?:pce|lubricador|preventor)[^.\n]{0,60}\d{3,5}\s*psi[^.\n]{0,30}\d+\s*min"],
             "hint": "lubricador probado a 5000 psi x 15 min", "standard": "API 53 / práctica PCE"},
            {"key": "correlacion", "label": "Correlación de profundidad (CCL)", "short": "CCL", "priority": "recomendado",
             "any": [r"\bccl\b", r"correlaci[oó]n"],
             "hint": "correlación con CCL", "standard": "Práctica de wireline"},
            {"key": "tension", "label": "Tensión de línea antes/después (lb)", "short": "tensión", "priority": "recomendado",
             "any": [r"tensi[oó]n[^.\n]{0,40}\d+\s*(?:lb|lbs)", r"\d+\s*lbs?\s+de\s+tensi[oó]n"],
             "hint": "tensión 1800 lb antes / 1750 lb después", "standard": "Práctica de wireline"},
            {"key": "detonacion", "label": "Verificación de detonación 100%", "short": "detonación", "priority": "requerido",
             "any": [r"deton[oó]", r"100\s*%", r"dispar[oó]"],
             "hint": "detonación 100% verificada en superficie", "standard": "API RP 67"},
        ],
    },
    "RIG_MOVE": {
        "label": "Movilización / arme / desarme",
        "detect": [r"movilizaci[oó]n", r"\br/[dmru]\b", r"cargas?", r"desarme", r"\barme\b", r"lump\s*sum"],
        "fields": [
            {"key": "fases", "label": "Avance R/D, R/M y R/U (%)", "short": "R/D-R/M-R/U", "priority": "requerido",
             "all": [r"r/d\s*[:=]?\s*\d+(?:\.\d+)?\s*%", r"r/m\s*[:=]?\s*\d+(?:\.\d+)?\s*%", r"r/u\s*[:=]?\s*\d+(?:\.\d+)?\s*%"],
             "hint": "R/D: 100% · R/M: 75% (3/4 cargas) · R/U: 25%", "standard": "Contrato de movilización"},
            {"key": "cargas", "label": "Conciliación de cargas (x/y)", "short": "cargas", "priority": "requerido",
             "any": [r"\d+\s*/\s*\d+\s*cargas?"],
             "hint": "3/4 cargas", "standard": "Contrato de movilización"},
            {"key": "recibo", "label": "Hora de recibo de equipo / tarifa", "short": "recibo", "priority": "requerido",
             "any": [r"recibi[oó]\s+equipo", r"recibo\s+de\s+equipo", r"tarifa"],
             "hint": "recibió equipo a las 08:00 del 01-Nov-2026", "standard": "Contrato (lump sum vs day rate)"},
            {"key": "horas", "label": "Horas totales del movimiento", "short": "horas", "priority": "recomendado",
             "any": [r"\d+(?:\.\d+)?\s*(?:h|hrs?|horas)\b"],
             "hint": "9.0 h totales", "standard": "Contrato de movilización"},
            {"key": "distancia", "label": "Distancia entre locaciones", "short": "distancia", "priority": "recomendado",
             "any": [r"\d+(?:\.\d+)?\s*(?:m|km|mts)\b", r"mismo\s+pad"],
             "hint": "35 m / 42 km", "standard": "Logística"},
        ],
    },
    "ESP": {
        "label": "Levantamiento artificial (ESP/BES, varillas, gas lift)",
        "detect": [r"\besp\b", r"\bbes\b", r"electrosumergible", r"megger", r"motor", r"superbandas?",
                   r"varillas?", r"gas\s*lift", r"bomba\s+(?:electro|de\s+cavidad)"],
        "fields": [
            {"key": "megger", "label": "Prueba de aislamiento (MΩ / GΩ, FF y FT)", "short": "megger", "priority": "requerido",
             "any": [r"\d+(?:\.\d+)?\s*(?:m|g|k)?(?:ohm|Ω)", r"megger[^.\n]{0,40}\d"],
             "hint": "Megger FT 2.4 MΩ / FF 1.6 Ω", "standard": "Práctica ESP"},
            {"key": "equipo", "label": "Equipo intervenido (motor/bomba/protector)", "short": "equipo", "priority": "requerido",
             "any": [r"motor", r"bomba", r"protector", r"separador", r"varilla"],
             "hint": "motor 4 kV + bomba 63 etapas", "standard": "IADC DOR"},
            {"key": "cable", "label": "Cable y accesorios (ft, MLE, superbandas)", "short": "cable", "priority": "recomendado",
             "any": [r"cable[^.\n]{0,40}\d+\s*ft", r"mle", r"superbandas?[^.\n]{0,20}\d"],
             "hint": "5518 ft de cable #4 + 4 superbandas/junta", "standard": "Práctica ESP"},
            {"key": "dictamen", "label": "Dictamen / causa de falla", "short": "dictamen", "priority": "recomendado",
             "any": [r"falla", r"dictamen", r"cortocircuito", r"a\s+tierra", r"aislamiento\s+bajo"],
             "hint": "dictamen: falla eléctrica en motor", "standard": "Análisis de falla"},
            {"key": "partes", "label": "Conciliación de partes (instaladas/recuperadas)", "short": "partes", "priority": "recomendado",
             "any": [r"recuper[oó]", r"instal[oó]", r"\d+\s*(?:partes|elementos)"],
             "hint": "2 bombas instaladas / 2 recuperadas", "standard": "Control de inventario"},
        ],
    },
    "NPT": {
        "label": "Tiempo no productivo (NPT)",
        "detect": [r"\bnpt\b", r"tormenta", r"suspendi[oó]", r"stand\s*by", r"lluvia", r"parada"],
        "fields": [
            {"key": "causa", "label": "Causa clasificada (clima/mecánica/espera/seguridad)", "short": "causa", "priority": "requerido",
             "any": [r"clima", r"tormenta", r"mec[aá]nic", r"espera", r"seguridad", r"stand\s*by"],
             "hint": "clima — tormenta eléctrica", "standard": "IADC NPT"},
            {"key": "codigo", "label": "Clasificación / código NPT", "short": "código NPT", "priority": "recomendado",
             "any": [r"npt[- ]?[a-z]{3}", r"\bn[- ]?(?:i{1,3}|iv)\b", r"c[oó]digo"],
             "hint": "NPT-WTR (clima), nivel II", "standard": "Contrato / IADC"},
        ],
    },
    "SAFETY": {
        "label": "Charla de seguridad / PJSM",
        "detect": [r"charla", r"reuni[oó]n\s+(?:de\s+)?seguridad", r"pjsm", r"preoperacional", r"checklist"],
        "fields": [
            {"key": "tema", "label": "Tema de la charla", "short": "tema", "priority": "requerido",
             "any": [r"charla[^.\n]{0,40}", r"reuni[oó]n[^.\n]{0,40}", r"pjsm[^.\n]{0,40}"],
             "hint": "charla preoperacional para balanceo de tapón", "standard": "Práctica HSE"},
            {"key": "asistentes", "label": "Personal asistente", "short": "asistentes", "priority": "recomendado",
             "any": [r"personal", r"taladro", r"cuadrilla", r"\d+\s*personas"],
             "hint": "todo el personal del taladro", "standard": "Práctica HSE"},
            {"key": "checklist", "label": "Checklist / JSA", "short": "checklist", "priority": "recomendado",
             "any": [r"checklist", r"\bjsa\b", r"\bast\b", r"permiso"],
             "hint": "checklist diario y JSA firmados", "standard": "Práctica HSE"},
        ],
    },
    "WELLHEAD": {
        "label": "Wellhead / árbol / BOP arme",
        "detect": [r"\b[aá]rbol\b", r"cabeza\s+de\s+pozo", r"wellhead", r"preventoras?", r"n/[ud]\b"],
        "fields": [
            {"key": "componente", "label": "Componente (árbol, cabezal, BOP)", "short": "componente", "priority": "requerido",
             "any": [r"[aá]rbol", r"cabeza", r"preventoras?", r"bop", r"spool"],
             "hint": 'árbol de producción 7-1/16" 5K', "standard": "API 6A / 16A"},
            {"key": "prueba", "label": "Prueba de presión posterior (psi x min)", "short": "prueba", "priority": "requerido",
             "any": [r"\d{3,5}\s*psi[^.\n]{0,30}\d+\s*min"],
             "hint": "probado a 3000 psi x 10 min", "standard": "API 53"},
            {"key": "torque", "label": "Torque de conexiones / ajuste", "short": "torque", "priority": "recomendado",
             "any": [r"torque", r"ft[- ]?lb", r"ajust[oó]"],
             "hint": "torque 300 ft-lb", "standard": "API 6A"},
        ],
    },
    "FISHING": {
        "label": "Pesca (Fishing)",
        "detect": [r"\bpesca\b", r"pescante", r"\bovershot\b", r"\bspear\b", r"im[aá]n", r"cesta", r"pez\b", r"fishing"],
        "fields": [
            {"key": "herramienta", "label": "Herramienta de pesca (overshot, spear, imán, OD)", "short": "herramienta", "priority": "requerido",
             "any": [r"overshot", r"spear", r"im[aá]n", r"pescante", r"junk\s*basket", r"grap[al]"],
             "hint": 'overshot 5-3/4" con grapa 3-1/2"', "standard": "IADC DOR"},
            {"key": "cota", "label": "Tope del pez / cota de enganche (ft)", "short": "cota pez", "priority": "requerido",
             "any": [r"(?:tof|tope|pez|enganch[oó]|@)[^.\n]{0,30}\d{3,5}(?:\.\d+)?\s*ft", r"\d{3,5}(?:\.\d+)?\s*ft"],
             "hint": "tope del pez @ 5410 ft MD", "standard": "IADC DOR"},
            {"key": "resultado", "label": "Resultado / tracción aplicada (klb)", "short": "resultado", "priority": "requerido",
             "any": [r"enganch[oó]", r"recuper[oó]", r"liber[oó]", r"sin\s+pesca", r"\d+(?:\.\d+)?\s*klb"],
             "hint": "enganchó pez y tensionó 75 klb; recuperó en superficie", "standard": "Práctica de pesca"},
        ],
    },
    "MILLING": {
        "label": "Molienda / limpieza mecánica (Milling)",
        "detect": [r"\bmolienda\b", r"\bmolino\b", r"\bmoli[oó]\b", r"\bmilling\b", r"rot[oó]\s+con\s+molino", r"escariador", r"scraper"],
        "fields": [
            {"key": "herramienta", "label": "Tipo y diámetro de molino / scraper", "short": "molino/OD", "priority": "requerido",
             "any": [r"(?:molino|mill|scraper|escariador)[^.\n]{0,30}\d", r"\d+(?:-\d+/\d+)?\"?\s*(?:molino|mill|scraper)"],
             "hint": 'molino plano 6-1/8"', "standard": "IADC DOR"},
            {"key": "intervalo", "label": "Intervalo molido (desde/hasta ft)", "short": "intervalo", "priority": "requerido",
             "any": [r"\d{3,5}(?:\.\d+)?\s*ft\s*(?:a|hasta|-)\s*\d{3,5}", r"desde\s+\d{3,5}\s*ft\s+hasta\s+\d{3,5}"],
             "hint": "desde 5330 ft hasta 5385 ft", "standard": "IADC DOR"},
            {"key": "parametros", "label": "Parámetros (WOB, RPM, caudal)", "short": "WOB/RPM", "priority": "requerido",
             "all": [r"\b\d+(?:\.\d+)?\s*klb\b", r"\b\d+\s*rpm\b"],
             "hint": "WOB 4 klb, 60 RPM, bombeando @ 2.5 bpm", "standard": "Práctica de molienda"},
        ],
    },
    "STIMULATION": {
        "label": "Estimulación / Acidificación",
        "detect": [r"estimulaci[oó]n", r"acidificaci[oó]n", r"\b[aá]cido\b", r"\bhcl\b", r"\bhf\b", r"inyectividad", r"fractura"],
        "fields": [
            {"key": "fluido", "label": "Tipo, concentración y volumen de tratamiento", "short": "tratamiento", "priority": "requerido",
             "all": [r"\d+(?:\.\d+)?\s*bbl", r"(?:hcl|hf|[aá]cido|surfactante|solvente|estimulaci[oó]n|salmuera)"],
             "hint": "30 bbl HCl 15% + 10 bbl preflujo", "standard": "API / HSE químicos"},
            {"key": "presion_tasa", "label": "Presión y tasa de bombeo (psi / bpm)", "short": "psi/bpm", "priority": "requerido",
             "all": [r"\d{2,5}\s*psi", r"\d+(?:\.\d+)?\s*bpm"],
             "hint": "a 2.5 bpm con 1850 psi máx", "standard": "Práctica de estimulación"},
            {"key": "desplazamiento", "label": "Desplazamiento final (bbl)", "short": "desplazamiento", "priority": "recomendado",
             "any": [r"desplaz[oó][^.\n]{0,40}\d+\s*bbl", r"overflush[^.\n]{0,30}\d+\s*bbl"],
             "hint": "desplazó con 45 bbl de salmuera", "standard": "Práctica de estimulación"},
        ],
    },
    "COILED_TUBING": {
        "label": "Coiled Tubing (CT)",
        "detect": [r"coiled\s*tubing", r"\bct\b", r"tuber[ií]a\s+flexible", r"inyector", r"bha\s+de\s+ct"],
        "fields": [
            {"key": "od", "label": "Diámetro de CT (pulgadas)", "short": "OD CT", "priority": "requerido",
             "any": [r"(?:ct|coiled\s*tubing|tuber[ií]a\s+flexible)[^.\n]{0,25}\d(?:-\d/\d)?\"?", r"\b(1-1/2|1-3/4|2|2-3/8)\""],
             "hint": 'CT 1-3/4"', "standard": "API RP 5C7"},
            {"key": "cotas", "label": "Cotas desde/hasta (ft)", "short": "cotas", "priority": "requerido",
             "any": [r"\d{3,5}(?:\.\d+)?\s*ft\s*(?:a|hasta|-)\s*\d{3,5}", r"hasta\s+\d{3,5}\s*ft"],
             "hint": "desde superficie hasta 6150 ft", "standard": "IADC DOR"},
            {"key": "hidraulica", "label": "Tasa y presión de bombeo (bpm / psi)", "short": "bpm/psi", "priority": "requerido",
             "all": [r"\d+(?:\.\d+)?\s*bpm", r"\d{2,5}\s*psi"],
             "hint": "bombeando N2/agua @ 1.8 bpm con 2400 psi", "standard": "Práctica CT"},
        ],
    },
    "SWABBING": {
        "label": "Achique / Swabbing / Prueba de producción",
        "detect": [r"\bswab(?:bing)?\b", r"achique", r"copas\s+de\s+swab", r"nivel\s+de\s+fluido"],
        "fields": [
            {"key": "corridas", "label": "Número de corridas / profundidad de copa (ft)", "short": "corridas/cota", "priority": "requerido",
             "any": [r"\d+\s*corridas?", r"hasta\s+\d{3,5}\s*ft", r"@\s*\d{3,5}\s*ft"],
             "hint": "8 corridas de swab hasta 4200 ft", "standard": "IADC DOR"},
            {"key": "recuperado", "label": "Volumen recuperado y BSW / fluido", "short": "volumen/BSW", "priority": "requerido",
             "any": [r"\d+(?:\.\d+)?\s*bbl", r"bsw", r"crudo", r"agua"],
             "hint": "recuperó 28 bbl (60% agua, 40% crudo)", "standard": "Práctica de producción"},
            {"key": "nivel", "label": "Nivel inicial / final (ft)", "short": "nivel fluido", "priority": "recomendado",
             "any": [r"nivel[^.\n]{0,30}\d{3,5}\s*ft"],
             "hint": "nivel inicial 1200 ft, final 2800 ft", "standard": "Práctica de producción"},
        ],
    },
}

REPORT_LEVEL_FIELDS = [
    {"key": "pozo", "label": "Nombre del pozo", "short": "pozo", "priority": "requerido",
     "any": [r"pozo\s*[:#]?\s*\S+", r"\bwell\s*[:#]?\s*\S+", r"yopo[- ]?\d"],
     "hint": "POZO: Yopo-1", "standard": "IADC DOR"},
    {"key": "fecha", "label": "Fecha del reporte", "short": "fecha", "priority": "requerido",
     "any": [r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", r"\b\d{1,2}[- ](?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"],
     "hint": "01-Nov-2026", "standard": "IADC DOR"},
    {"key": "equipo", "label": "Equipo / taladro", "short": "equipo", "priority": "recomendado",
     "any": [r"equipo\s*[:#]?\s*\S+", r"taladro\s*[:#]?\s*\S+", r"\brig\s*[:#]?\s*\S+", r"err\s+tsw"],
     "hint": "Equipo: ERR TSW-01", "standard": "IADC DOR"},
    {"key": "operadora", "label": "Operadora / contratista", "short": "operadora", "priority": "recomendado",
     "any": [r"operadora\s*[:#]?\s*\S+", r"operador\s*[:#]?\s*\S+", r"operator\s*[:#]?\s*\S+", r"contratista\s*[:#]?\s*\S+"],
     "hint": "Operadora: Sabana Resources / Contratista: TSW", "standard": "IADC DOR"},
    {"key": "fluido", "label": "Fluido de pozo y densidad (ppg)", "short": "fluido de pozo", "priority": "recomendado",
     "any": [r"\d+(?:\.\d+)?\s*ppg"],
     "hint": "9.2 ppg KCl", "standard": "Práctica de fluidos"},
    {"key": "dia", "label": "Día en el pozo / días planeados", "short": "día de operación", "priority": "recomendado",
     "any": [r"d[ií]a\s+\d+", r"day\s+\d+"],
     "hint": "Día 4 de 8", "standard": "IADC DOR"},
]


def _compile(patterns: List[str]) -> List[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


for _op in OPS.values():
    for _f in _op["fields"]:
        if "any" in _f:
            _f["_any"] = _compile(_f["any"])
        if "all" in _f:
            _f["_all"] = _compile(_f["all"])
    _op["_detect"] = _compile(_op["detect"])

for _f in REPORT_LEVEL_FIELDS:
    _f["_any"] = _compile(_f["any"])


def _field_status(text: str, f: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """(presente, texto detectado)."""
    if "_all" in f:
        if all(p.search(text) for p in f["_all"]):
            for p in f["_all"]:
                m = p.search(text)
                if m:
                    return True, m.group(0)
        return False, None
    for p in f.get("_any", []):
        m = p.search(text)
        if m:
            return True, m.group(0)
    return False, None


# Precedencia cuando un evento menciona varias cosas: manda la maniobra principal
OP_ORDER = ["HMBP", "CEMENT_PLUG", "BOP_TEST", "FISHING", "MILLING", "STIMULATION",
            "COILED_TUBING", "SWABBING", "WIRELINE", "RIG_MOVE", "ESP",
            "POOH", "RIH", "WELLHEAD", "CIRCULATION", "NPT", "SAFETY"]


def detect_ops(text: str) -> List[str]:
    """Operaciones detectadas, ordenadas por precedencia (la primera es la principal)."""
    found = [op for op, spec in OPS.items() if any(p.search(text) for p in spec["_detect"])]
    return sorted(found, key=lambda o: OP_ORDER.index(o) if o in OP_ORDER else 99)


def _fields_for(op: str, text: str) -> List[Dict[str, Any]]:
    spec = OPS[op]
    if "variants" in spec:
        for pat, name in spec.get("variant_detect", []):
            if re.search(pat, text, re.IGNORECASE):
                keys = set(spec["variants"][name])
                return [f for f in spec["fields"] if f["key"] in keys]
    return spec["fields"]


def check_event(text: str, report_text: str = "") -> List[Dict[str, Any]]:
    """
    Evalúa la operación PRINCIPAL del evento (una por línea, como se reporta en campo).
    Los campos con scope='report' se buscan en todo el reporte (ej. especificación
    del tubular, que se declara una vez y no en cada línea).
    """
    ops = detect_ops(text)
    if not ops:
        return []
    op = ops[0]
    fields = _fields_for(op, text)
    ok_fields, missing = [], []
    for f in fields:
        haystack = report_text if f.get("scope") == "report" else text
        present, found = _field_status(haystack, f)
        entry = {
            "key": f["key"], "label": f["label"], "short": f["short"],
            "priority": f["priority"], "hint": f["hint"], "standard": f["standard"],
        }
        if present:
            entry["detected"] = found
            ok_fields.append(entry)
        else:
            missing.append(entry)
    total = sum(2 if f["priority"] == "requerido" else 1 for f in fields)
    earned = sum(2 if e["priority"] == "requerido" else 1 for e in ok_fields)
    return [{
        "op": op,
        "label": OPS[op]["label"],
        "score": round(100 * earned / total) if total else 100,
        "ok": ok_fields,
        "missing": missing,
        "also_detected": ops[1:],
        "points_total": total,
        "points_earned": earned,
    }]


def report_level_check(text: str, meta: Dict[str, str],
                       well_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    haystack = text + "\n" + "\n".join(f"{k}: {v}" for k, v in meta.items())
    if well_state and well_state.get("fluid"):
        haystack += f"\nfluido_previo: {well_state['fluid']}"
    ok, missing = [], []
    for f in REPORT_LEVEL_FIELDS:
        present, found = _field_status(haystack, f)
        entry = {"key": f["key"], "label": f["label"], "short": f["short"],
                 "priority": f["priority"], "hint": f["hint"], "standard": f["standard"]}
        if present:
            entry["detected"] = found
            ok.append(entry)
        else:
            missing.append(entry)
    total = sum(2 if f["priority"] == "requerido" else 1 for f in REPORT_LEVEL_FIELDS)
    earned = sum(2 if e["priority"] == "requerido" else 1 for e in ok)
    return {"score": round(100 * earned / total) if total else 100, "ok": ok, "missing": missing}


def evaluate(events_and_text: List[Dict[str, Any]], raw_text: str,
             meta: Dict[str, str],
             well_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    events_and_text: [{"id":1,"from":"07:00","to":"08:00","text":"...","line":1}]
    Devuelve completitud por evento/operación + faltantes consolidados.
    """
    # 1) Detectar la operación principal de cada evento (en orden cronológico)
    seq: List[Dict[str, Any]] = []
    for ev in events_and_text:
        checks = check_event(ev["text"], raw_text)
        if not checks:
            continue
        c = checks[0]
        seq.append({"ev": ev, "op": c["op"], "label": c["label"],
                    "text": ev["text"], "missing": [], "ok": []})

    # 2) Agrupar eventos consecutivos de la misma operación (una maniobra puede
    #    ocupar varios bloques horarios: sentar HMBP y luego liberarlo/probarlo).
    groups: List[Dict[str, Any]] = []
    for item in seq:
        if groups and groups[-1]["op"] == item["op"]:
            g = groups[-1]
            g["text"] += " " + item["text"]
            g["events"].append(item["ev"])
            g["to"] = item["ev"]["to"]
        else:
            groups.append({
                "op": item["op"], "label": item["label"], "text": item["text"],
                "events": [item["ev"]], "from": item["ev"]["from"], "to": item["ev"]["to"],
            })

    by_op: List[Dict[str, Any]] = []
    markers: Dict[int, List[str]] = {}
    for g in groups:
        fields = _fields_for(g["op"], g["text"])
        ok_fields, missing = [], []
        for f in fields:
            haystack = raw_text if f.get("scope") == "report" else g["text"]
            present, found = _field_status(haystack, f)
            if not present and well_state and f["key"] == "tubular" and well_state.get("tubular"):
                present = True
                found = f"[Continuidad] {well_state['tubular']}"
            entry = {"key": f["key"], "label": f["label"], "short": f["short"],
                     "priority": f["priority"], "hint": f["hint"], "standard": f["standard"]}
            if present:
                entry["detected"] = found
                ok_fields.append(entry)
            else:
                missing.append(entry)
        total = sum(2 if f["priority"] == "requerido" else 1 for f in fields)
        earned = sum(2 if e["priority"] == "requerido" else 1 for e in ok_fields)
        first = g["events"][0]
        last = g["events"][-1]
        by_op.append({
            "op": g["op"], "label": g["label"], "text": g["text"],
            "event": first["id"], "from": g["from"], "to": g["to"],
            "line": first["line"], "score": round(100 * earned / total) if total else 100,
            "ok": ok_fields, "missing": missing,
            "points_total": total, "points_earned": earned,
            "span_events": len(g["events"]),
        })
        # Solo se marca en el texto lo OBLIGATORIO; lo recomendado va al checklist
        req_missing = [m["short"] for m in missing if m["priority"] == "requerido"]
        if req_missing:
            markers.setdefault(last["id"], []).extend(req_missing)

    # dedupe markers manteniendo orden
    for k, v in markers.items():
        seen, out = set(), []
        for x in v:
            if x not in seen:
                seen.add(x)
                out.append(x)
        markers[k] = out[:6]

    op_total = sum(c["points_total"] for c in by_op)
    op_earned = sum(c["points_earned"] for c in by_op)

    rl = report_level_check(raw_text, meta, well_state=well_state)
    # La completitud global pesa 70% operaciones y 30% encabezado
    op_score = round(100 * op_earned / op_total) if op_total else 100
    score = round(0.7 * op_score + 0.3 * rl["score"]) if by_op else rl["score"]

    if score >= 85:
        level = "Completo"
    elif score >= 65:
        level = "Aceptable"
    elif score >= 40:
        level = "Incompleto"
    else:
        level = "Muy incompleto"

    missing_all: List[Dict[str, Any]] = []
    seen_missing = set()
    for c in by_op:
        for m in c["missing"]:
            if m["priority"] != "requerido":
                continue
            dedupe_key = (c["op"], m["key"])
            if dedupe_key in seen_missing:
                continue
            seen_missing.add(dedupe_key)
            missing_all.append({**m, "op": c["op"], "op_label": c["label"],
                                "event": c["event"], "from": c["from"], "to": c["to"]})

    return {
        "score": score,
        "operation_score": op_score,
        "header_score": rl["score"],
        "level": level,
        "by_operation": by_op,
        "header": rl,
        "markers": markers,
        "missing_required": missing_all,
        "ops_detected": sorted({c["op"] for c in by_op}),
    }
