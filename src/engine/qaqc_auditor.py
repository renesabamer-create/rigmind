"""
Auditoría con IA (una sola llamada, multi-proveedor).

Este módulo solo se encarga de: construir el prompt, llamar al proveedor
elegido y devolver un JSON validado. Las reglas deterministas, la completitud
y la verificación numérica viven en `auditor.py` y `completeness.py`.

Proveedores soportados: DeepSeek, OpenAI, Anthropic, Groq y Gemini.
Si el proveedor no está implementado, devuelve None para que el orquestador
lo reporte explícitamente (nunca falla en silencio).
"""

import json
import re
from typing import Any, Dict, Optional

from src.engine.llm_network import detect_provider, execute_llm_request
from src.engine.learning_memory import select_relevant_examples

# ---------------------------------------------------------------------------
# Prompt del auditor
# ---------------------------------------------------------------------------
AUDIT_SYSTEM_PROMPT = """Eres un superintendente de operaciones de pozo y auditor técnico QA/QC.
Recibes las notas de campo, en español, de una operación de intervención de pozo que cubre un lapso de tiempo (puede ser un turno parcial, no necesariamente 00:00-24:00).

TU ÚNICA MISIÓN es devolver el reporte saneado en español y los hallazgos técnicos.

REGLAS INQUEBRANTABLES:
1. CERO OMISIÓN: conserva cada maniobra, cifra, unidad, presión, volumen, cota, tiempo y número de parte. No resumas ni elimines actividades.
2. CERO INVENCIÓN: no inventes fechas, horas, presiones, cotas ni cantidades. Si un dato falta, NO lo completes: escribe `[completar: nombre del dato]` en el punto exacto. Si un dato es imposible (fecha inexistente, peso absurdo, resta que no cuadra), NO lo cambies por otro: repórtalo en `agent_findings` y déjalo visible con una nota entre corchetes.
3. NO INSERTES placeholders para datos que YA están presentes. Un reporte completo debe quedar limpio.
4. CRONOLOGÍA: respeta el lapso real del reporte. Mantén el formato `HH:MM - HH:MM: actividad` por línea. Si el reporte usa solo hora de inicio, infiere el fin con la siguiente actividad y reporta el cambio. No fuerces un cierre de 24 h si el turno no lo es.
5. TERMINOLOGÍA: corrige tipeo de campo y normaliza al español técnico (pup joint de manejo, manifold de choque, MLE, overcoupling, carta Barton, trip tank, HMBP). No traduzcas al inglés en esta fase.
6. ESTILO: una maniobra por oración, en pasado, con su parámetro medible. Reemplaza "ok" por el criterio de aceptación (ej. "0 psi de caída en 15 min").

HALLAZGOS (`agent_findings`): cada hallazgo debe poder verificarse. Usa este objeto:
{
  "agent": "tally | cementing | bop | well-control | chrono | esp | wireline | hse | rig-move | completitud",
  "severity": "critical | warning | info | success",
  "badge": "EMOJI + TÍTULO CORTO",
  "message": "qué está mal o qué se verificó, con la cifra y el criterio",
  "standard": "norma o práctica aplicable (API 53, API RP 59, NORSOK D-010, API Spec 5CT, práctica del fabricante...) o null",
  "suggestion": "corrección concreta que el usuario puede aplicar, o null",
  "evidence": {"line": 4, "quote": "fragmento corto del texto original"} o null
}
Clasifica como `critical` solo lo que cambia el sentido técnico o la seguridad (aritmética errada, presión fuera de norma, barrera no verificada). No inventes hallazgos para llenar la lista.

SALIDA: un único objeto JSON válido, sin markdown, con esta forma:
{
  "corrected_spanish": "reporte saneado en español, línea por línea, sin títulos decorativos",
  "agent_findings": [ ... ],
  "learning_tips": ["consejo pedagógico corto y accionable", "..."]
}"""


def parse_audit_json(raw_resp: str) -> Dict[str, Any]:
    clean = (raw_resp or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean.strip())
    except Exception:
        m = re.search(r"\{[\s\S]*\}", clean)
        if m:
            return json.loads(m.group(0))
        raise ValueError("La IA no devolvió un JSON válido")


def _user_msg(text: str, well_name: str) -> str:
    examples = select_relevant_examples(text, limit=2)
    ex_block = ""
    if examples:
        lines = []
        for ex in examples:
            op = ex.get("operation") or "Operación"
            es = (ex.get("spanish_exemplar") or "").strip()[:350]
            if es:
                lines.append(f"- [{op}]: {es}")
        if lines:
            ex_block = (
                "EJEMPLOS APROBADOS POR EL USUARIO (imita este nivel de detalle y redacción):\n"
                + "\n".join(lines)
                + "\n\n"
            )
    return (f"Pozo: {well_name}\n"
            f"{ex_block}"
            f"Notas crudas del lapso (auditar, sanear y completar sin inventar):\n\n{text}")


def _msg_openai(text: str, well_name: str) -> list:
    return [
        {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
        {"role": "user", "content": _user_msg(text, well_name)},
    ]


def call_ai_spanish_audit(text: str, api_key: str, provider: str = "auto",
                          well_name: str = "Well") -> Optional[Dict[str, Any]]:
    k = (api_key or "").strip()
    if not k:
        return None
    prov = detect_provider(k, requested=provider)

    if prov == "deepseek":
        payload = {
            "model": "deepseek-chat",
            "messages": _msg_openai(text, well_name),
            "temperature": 0.1,
            "max_tokens": 8192,
            "response_format": {"type": "json_object"},
        }
        return _call_openai_like("https://api.deepseek.com/chat/completions", payload,
                                 {"Authorization": f"Bearer {k}"}, prov)

    if prov == "openai":
        payload = {
            "model": "gpt-4o-mini",
            "messages": _msg_openai(text, well_name),
            "temperature": 0.1,
            "max_tokens": 8192,
            "response_format": {"type": "json_object"},
        }
        return _call_openai_like("https://api.openai.com/v1/chat/completions", payload,
                                 {"Authorization": f"Bearer {k}"}, prov)

    if prov == "groq":
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": _msg_openai(text, well_name),
            "temperature": 0.1,
            "max_tokens": 8192,
        }
        return _call_openai_like("https://api.groq.com/openai/v1/chat/completions", payload,
                                 {"Authorization": f"Bearer {k}"}, prov)

    if prov == "anthropic":
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "max_tokens": 8192,
            "temperature": 0.1,
            "system": AUDIT_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": _user_msg(text, well_name)}],
        }
        res = execute_llm_request("https://api.anthropic.com/v1/messages", payload,
                                  {"x-api-key": k, "anthropic-version": "2023-06-01"}, timeout=60)
        parts = res.get("content", [])
        out = "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
        return parse_audit_json(out) if out else None

    if prov == "gemini":
        payload = {
            "system_instruction": {"parts": [{"text": AUDIT_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": _user_msg(text, well_name)}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192,
                                 "responseMimeType": "application/json"},
        }
        last_err: Optional[Exception] = None
        for model in ("gemini-flash-latest", "gemini-2.5-flash"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={k}"
            try:
                res = execute_llm_request(url, payload, {"Content-Type": "application/json"}, timeout=60)
            except Exception as e:
                last_err = e
                continue
            cands = res.get("candidates", [])
            if cands:
                parts = cands[0].get("content", {}).get("parts", [])
                out = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                if out:
                    return parse_audit_json(out)
        raise RuntimeError(f"Gemini no respondió: {last_err}")

    return None


def _call_openai_like(url: str, payload: dict, headers: dict, prov: str) -> Optional[Dict[str, Any]]:
    try:
        res = execute_llm_request(url, payload, headers, timeout=60)
    except RuntimeError as e:
        # Algunos proveedores no aceptan response_format json_object
        if "response_format" in str(e).lower() or "json" in str(e).lower():
            payload.pop("response_format", None)
            res = execute_llm_request(url, payload, headers, timeout=60)
        else:
            raise
    choices = res.get("choices", [])
    if not choices:
        return None
    content = choices[0].get("message", {}).get("content", "")
    if not content.strip():
        return None
    return parse_audit_json(content)
