"""
Reglas de texto compartidas por el auditor y el traductor.

Una sola fuente de verdad para:
  - Glosario ES -> EN petrolero (se inyecta en el prompt de traducción).
  - Correcciones de tipeo de campo (solo casos inequívocos).
  - Detección de frases vacías ("se continúa", "ok" suelto...).
  - Extracción de pares número+unidad (para verificar paridad real).
  - Detección de español residual (para no decir "certificado" sin evidencia).
"""

import re
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# 1. GLOSARIO ES -> EN (términos y siglas que el reporte debe usar)
#    Orden: de más específico a más general. Se inyecta en el prompt de IA y
#    se usa para verificar que la traducción conserve las siglas.
# ---------------------------------------------------------------------------
GLOSSARY: List[Tuple[str, str]] = [
    ("personal toma de alimentos y descanso", "crew meal and rest break"),
    ("personal tomando alimentos", "crew meal break"),
    ("reunión preoperacional", "pre-job safety meeting (PJSM)"),
    ("charla preoperacional", "pre-job safety meeting (PJSM)"),
    ("charla de seguridad", "safety meeting"),
    ("checklist diario", "daily tools and equipment inspection"),
    ("pup joint de manejo", "handling pup joint"),
    ("llaves hidráulicas", "hydraulic power tongs"),
    ("manifold de choque", "choke manifold"),
    ("conexiones de líneas", "plumbed surface lines"),
    ("circulación en directa", "forward circulation"),
    ("circulación en reversa", "reverse circulation"),
    ("píldora de limpieza", "cleanout pill"),
    ("goma xántica", "xanthan gum"),
    ("agua industrial", "industrial water"),
    ("agua fresca", "fresh water"),
    ("lechada de cemento", "cement slurry"),
    ("cemento clase g", "Class G cement"),
    ("tapón de fondo", "bottom cement plug"),
    ("tapón balanceado", "balanced cement plug"),
    ("tapón de cemento", "cement plug"),
    ("tapón puente", "bridge plug"),
    ("preflujo", "preflush"),
    ("espesor", "thickness"),
    ("desplazamiento", "displacement"),
    ("retorno limpio", "clean returns"),
    ("pozo lleno", "well full"),
    ("testigos", "surface witness samples"),
    ("succión en backflow", "backflow suction / U-tubing effect"),
    ("bridge plug hidromecánico", "hydro-mechanical bridge plug (HMBP)"),
    ("bola de asentamiento", "setting ball"),
    ("presurizó", "pressured up"),
    ("prueba de integridad", "pressure integrity test"),
    ("carta barton", "Barton circular pressure chart recorder"),
    ("bomba de cementación", "cementing unit"),
    ("preventoras", "BOP stack"),
    ("árbol de producción", "production tree (X-tree)"),
    ("cabeza de pozo", "wellhead"),
    ("tormenta eléctrica", "electrical storm"),
    ("sobretensión", "overpull"),
    ("vueltas a la derecha", "right-hand (RH) turns"),
    ("liberó del hmbp", "released from HMBP"),
    ("sin arrastre", "w/o drag"),
    ("peso neutro", "neutral weight"),
    ("tubería combinada", "tapered workstring"),
    ("tubería llena", "wet string (tubing full)"),
    ("tubería seca", "dry string"),
    ("a rack", "to pipe racks"),
    ("quebrando", "breaking out"),
    ("sencillos", "singles"),
    ("paradas", "stands"),
    ("avance", "progress"),
    ("juntas", "joints (jts)"),
    ("empacadura", "packer"),
    ("válvula de seguridad", "SCSSV"),
    ("niple de asiento", "landing nipple"),
    ("camisa deslizante", "sliding sleeve (SSD)"),
    ("mandril de bolsillo", "side pocket mandrel (SPM)"),
    ("válvula de gas lift", "gas lift valve (GLV)"),
    ("bomba electrosumergible", "electrical submersible pump (ESP)"),
    ("bomba de cavidad progresiva", "progressing cavity pump (PCP)"),
    ("varilla pulida", "polished rod"),
    ("sarta de varillas", "sucker rod string"),
    ("cable mle", "motor lead extension (MLE)"),
    ("superbandas", "superbands"),
    ("overcoupling", "overcoupling"),
    ("megger", "megger test"),
    ("aislamiento", "insulation resistance"),
    ("fase-tierra", "phase-to-ground (FT)"),
    ("fase-fase", "phase-to-phase (FF)"),
    ("cañón de casing", "casing gun"),
    ("disparó", "perforated"),
    ("lubricador", "lubricator"),
    ("preventor anular", "annular preventer"),
    ("arietes", "rams"),
    ("prueba en baja", "low-pressure test"),
    ("prueba en alta", "high-pressure test"),
    ("acumulador koomey", "Koomey accumulator unit"),
    ("desarme", "rig down (R/D)"),
    ("arme", "rig up (R/U)"),
    ("movilización", "rig move"),
    ("cargas", "loads"),
    ("recibo de equipo", "rig acceptance / handover"),
    ("tarifa", "day rate"),
    ("reconocimiento de horas", "hour credit adjustment"),
    ("pozo", "well"),
    ("sarta", "string"),
    ("tubería", "tubing"),
    ("peso", "weight"),
    ("presión", "pressure"),
    ("caudal", "rate"),
    ("volumen", "volume"),
    ("densidad", "density"),
    ("profundidad", "depth"),
    ("velocidad", "speed"),
    ("arrastre", "drag"),
    ("cota", "depth (MD)"),
]

# ---------------------------------------------------------------------------
# 2. SIGLAS que un DOR en inglés debe conservar (para verificación objetiva)
# ---------------------------------------------------------------------------
ACRONYMS: Dict[str, str] = {
    "POOH": "Pulled Out Of Hole",
    "RIH": "Ran In Hole",
    "M/U": "Made Up",
    "B/O": "Broke Out",
    "L/D": "Laid Down",
    "N/U": "Nippled Up",
    "N/D": "Nippled Down",
    "R/U": "Rigged Up",
    "R/D": "Rigged Down",
    "R/M": "Rig Move",
    "WOC": "Waiting On Cement",
    "TOC": "Top Of Cement",
    "HMBP": "Hydro-Mechanical Bridge Plug",
    "BHA": "Bottom Hole Assembly",
    "PJSM": "Pre-Job Safety Meeting",
    "NPT": "Non-Productive Time",
    "PUW": "Pick-Up Weight",
    "SOW": "Slack-Off Weight",
    "ROTW": "Rotating Weight",
    "TBG": "Tubing",
    "CSG": "Casing",
    "CCL": "Casing Collar Locator",
    "PLT": "Production Logging Tool",
    "CBL": "Cement Bond Log",
    "ESP": "Electrical Submersible Pump",
    "PCE": "Pressure Control Equipment",
    "BOP": "Blowout Preventer",
    "SCSSV": "Surface Controlled Subsurface Safety Valve",
    "GLV": "Gas Lift Valve",
    "SPM": "Side Pocket Mandrel",
    "PCP": "Progressing Cavity Pump",
    "SSD": "Sliding Side Door",
    "MLE": "Motor Lead Extension",
}

# ---------------------------------------------------------------------------
# 3. CORRECCIONES DE TIPEO DE CAMPO (solo casos inequívocos)
#    (patrón, reemplazo, etiqueta para el hallazgo)
# ---------------------------------------------------------------------------
TYPO_RULES: List[Tuple[str, str, str]] = [
    (r"\bpup\s+joi\s*t(?:\s+de\s+manejo)?\b", "pup joint de manejo", "pup joint"),
    (r"\bxequipos\b", "equipos de superficie", "xequipos"),
    (r"\bmls\s+joints?\b", "MLE (Motor Lead Extension)", "mls joints"),
    (r"\bovercoupling\b", "overcouplings con superbandas", "overcoupling"),
    (r"\bcheck\s*list\b", "checklist", "check list"),
    (r"\blineas\b", "líneas", "lineas"),
    (r"\btuberia\b", "tubería", "tuberia"),
    (r"\brealizo\b", "realizó", "realizó"),
    (r"\bcontinuan\b", "continúan", "continúan"),
    (r"\bcirculacion\b", "circulación", "circulación"),
    (r"\btension[oó]?\s+con\s+(\d+(?:\.\d+)?)\s*klbs?\b", r"tensionó la sarta a \1 klb", "tensionó con"),
]

# Frases vacías que un auditor debe señalar (no se corrigen solas: se sugiere)
VAGUE_PHRASES: List[Tuple[str, str]] = [
    (r"\bse\s+contin[uú]a(?:ron)?\s+(?:con\s+)?(?:las\s+)?(?:operaciones|actividades|trabajos)\b",
     "Reemplace 'se continúa con las operaciones' por la maniobra concreta con cotas, juntas o presiones."),
    (r"\bse\s+realizaron?\s+(?:las\s+)?(?:actividades|trabajos|operaciones)\b",
     "Reemplace 'se realizaron actividades' por la operación específica y su parámetro medible."),
    (r"\b(?:varios|varias|algunos|algunas)\s+(?:jtas?|juntas?|bbl|psi|vueltas?)\b",
     "Cuantifique: un DOR no acepta 'varios' ni 'algunos'."),
    (r"\baprox(?:imadamente)?\.?\s*\d", "Reemplace 'aprox.' por el valor medido exacto."),
    (r"\b(?:qued[oó]|est[aá])\s+ok\b|\bok\s*[,.]?\s*$",
     "Cambie 'ok' suelto por el criterio de aceptación (ej. '0 psi de caída en 15 min')."),
]

# ---------------------------------------------------------------------------
# 4. NÚMEROS + UNIDAD (para paridad real y validaciones)
# ---------------------------------------------------------------------------
UNIT_ALIASES = {
    "ft": "ft", "pies": "ft", "pie": "ft",
    "m": "m", "mts": "m",
    "psi": "psi", "lppc": "psi",
    "bbl": "bbl", "bbls": "bbl",
    "bpm": "bpm",
    "ppg": "ppg",
    "klb": "klb", "klbs": "klb",
    "lb": "lb", "lbs": "lb", "lb/ft": "lb/ft", "#": "lb/ft",
    "min": "min", "minutos": "min", "mins": "min",
    "h": "h", "hr": "h", "hrs": "h", "horas": "h",
    "jtas": "jtas", "juntas": "jtas", "jts": "jtas", "jt": "jtas",
    "sx": "sx", "sacos": "sx",
    "gal": "gal",
    "°f": "°F", "°c": "°C",
    "%": "%",
}

NUMBER_UNIT_RE = re.compile(
    r"(?<![\w/])(\d+(?:[.,]\d+)?)\s*"
    r"(lb/ft|klbs?|bbls?|bpm|ppg|psi|ft|pies|mins?|minutos|hrs?|horas?|"
    r"jtas?|juntas|jts?|sx|sacos|gal|°f|°c|%|m|mts|lbs?|h)\b",
    re.IGNORECASE,
)


def extract_number_units(text: str) -> List[Tuple[str, str]]:
    """Devuelve [(valor_normalizado, unidad_normalizada)] en orden de aparición."""
    out: List[Tuple[str, str]] = []
    for m in NUMBER_UNIT_RE.finditer(text or ""):
        val = m.group(1).replace(",", ".")
        unit = UNIT_ALIASES.get(m.group(2).lower(), m.group(2).lower())
        out.append((val, unit))
    return out


# ---------------------------------------------------------------------------
# 5. ESPAÑOL RESIDUAL (para QA de traducción, sin falsos negativos burdos)
# ---------------------------------------------------------------------------
SPANISH_RESIDUE_RE = re.compile(
    r"\b(?:"
    r"del|de\s+la|de\s+los|para|por|con\s+el|con\s+la|hacia|hasta|desde|entre|"
    r"alimentos|descanso|conexiones|lineas|líneas|tuber[ií]a|manejo|equipos|"
    r"sacando|primeras|juntas|tension[oó]|corte|arme|desarme|bajo|sobre|"
    r"verific[oó]|baj[oó]|circul[oó]|desplaz[oó]|aplic[oó]|realiz[oó]|"
    r"presuriz[oó]|liber[oó]|sent[oó]|mezcl[oó]|recogi[oó]|evidenci[oó]|"
    r"llen[oó]|aplic[oó]|qued[oó]|inici[oó]|continu[oó]|suspendi[oó]|"
    r"retom[oó]|abri[oó]|cerr[oó]|subi[oó]|baj[oó]|peso|presi[oó]n|caudal|"
    r"volumen|densidad|profundidad|velocidad|arrastre|cota|avance|sarta|"
    r"pozo|equipo|taladro|cemento|lechada|tap[oó]n|espesor|preflujo|"
    r"agua|fresca|industrial|retorno|limpio|lleno|niple|camisa|varilla|"
    r"empacadura|válvula|preventor|ariete|prueba|integridad|acumulador|"
    r"recibo|tarifa|cargas|movilizaci[oó]n|tormenta|el[eé]ctrica|"
    r"clase|grado|rosca|pi[lda]|bola|asentamiento|anclaje|sobretensi[oó]n|"
    r"vueltas|derecha|izquierda|sin|cabeza|pozo|superficie"
    r")\b",
    re.IGNORECASE,
)


def spanish_residue(text: str) -> List[str]:
    """Palabras en español detectadas en el texto (deduplicadas, orden de aparición)."""
    seen, out = set(), []
    for m in SPANISH_RESIDUE_RE.finditer(text or ""):
        w = m.group(0).lower()
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.;:])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]
