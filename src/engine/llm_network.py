import json
import ssl
import urllib.request
import urllib.error
from typing import Dict, Any, Tuple, Optional

def get_ssl_context() -> ssl.SSLContext:
    """Returns a robust SSL context that works across Windows, Linux, and corporate proxies."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()

def detect_provider(key: str, requested: str = "auto") -> str:
    """Detects provider by key shape or explicit choice."""
    if requested and requested.lower() not in ("auto", "none", ""):
        return requested.lower()
    k = (key or "").strip()
    if k.startswith("sk-ant-"):
        return "anthropic"
    if k.startswith("gsk_"):
        return "groq"
    if k.startswith("sk-") and len(k) <= 36:
        return "deepseek"
    if k.startswith("sk-"):
        return "openai"
    if k.startswith("AIza"):
        return "gemini"
    if len(k) == 32:
        return "deepseek"
    return "deepseek"

def execute_llm_request(url: str, payload: dict, headers: dict, timeout: int = 40) -> dict:
    """
    Executes an HTTPS POST request to an LLM provider endpoint.
    Extracts explicit error descriptions from HTTPError response bodies.
    """
    headers = dict(headers)
    if "User-Agent" not in headers:
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RigMind/2.0"
    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    ctx = get_ssl_context()

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        err_msg = body
        try:
            parsed = json.loads(body)
            if "error" in parsed:
                err_val = parsed["error"]
                if isinstance(err_val, dict):
                    err_msg = err_val.get("message", body)
                elif isinstance(err_val, str):
                    err_msg = err_val
            elif "message" in parsed:
                err_msg = parsed["message"]
        except Exception:
            pass

        # Friendly interpretations for common oilfield users
        if e.code == 401:
            friendly = f"HTTP 401 (Autenticación fallida): Clave no válida o revocada. {err_msg}"
        elif e.code == 402 or "insufficient" in err_msg.lower() or "quota" in err_msg.lower():
            friendly = f"HTTP 402 (Saldo insuficiente): La cuenta no tiene créditos disponibles. Recargue saldo en la plataforma del proveedor. {err_msg}"
        elif e.code == 429:
            friendly = f"HTTP 429 (Límite de tasa excedido): Demasiadas solicitudes por minuto. {err_msg}"
        else:
            friendly = f"HTTP {e.code}: {err_msg}"

        raise RuntimeError(friendly)
    except urllib.error.URLError as e:
        raise RuntimeError(f"Error de red o conexión: {str(e.reason)}")
    except Exception as e:
        raise RuntimeError(f"Error inesperado de comunicación: {str(e)}")

def test_ai_provider_connection(api_key: str, provider: str = "auto") -> Dict[str, Any]:
    """
    Probes an LLM provider with a fast 1-token request to verify connectivity and credentials.
    """
    if not api_key or not api_key.strip():
        return {"success": False, "error": "La clave de API está vacía."}

    k = api_key.strip()
    prov = detect_provider(k, requested=provider)

    try:
        if prov == "deepseek":
            url = "https://api.deepseek.com/chat/completions"
            headers = {"Authorization": f"Bearer {k}"}
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            }
            res = execute_llm_request(url, payload, headers, timeout=12)
            return {"success": True, "provider": "deepseek", "model": "deepseek-chat", "message": "Conexión exitosa con DeepSeek (V3)"}

        elif prov == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {k}"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            }
            res = execute_llm_request(url, payload, headers, timeout=12)
            return {"success": True, "provider": "openai", "model": "gpt-4o-mini", "message": "Conexión exitosa con OpenAI (GPT-4o-mini)"}

        elif prov == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {k}"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            }
            res = execute_llm_request(url, payload, headers, timeout=12)
            return {"success": True, "provider": "groq", "model": "llama-3.3-70b-versatile", "message": "Conexión exitosa con Groq (Llama 3.3)"}

        elif prov == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": k,
                "anthropic-version": "2023-06-01"
            }
            payload = {
                "model": "claude-3-5-haiku-20241022",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            }
            res = execute_llm_request(url, payload, headers, timeout=12)
            return {"success": True, "provider": "anthropic", "model": "claude-3-5-haiku", "message": "Conexión exitosa con Anthropic (Claude 3.5)"}

        elif prov == "gemini":
            # Gemini models probe
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={k}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RigMind/2.0"})
            ctx = get_ssl_context()
            with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "models" in data:
                    return {"success": True, "provider": "gemini", "model": "gemini-2.0-flash", "message": "Conexión exitosa con Google Gemini"}
            return {"success": True, "provider": "gemini", "model": "gemini-2.0-flash", "message": "Conexión exitosa con Google Gemini"}

        else:
            return {"success": False, "error": f"Proveedor desconocido: '{prov}'"}

    except Exception as e:
        return {"success": False, "provider": prov, "error": str(e)}
