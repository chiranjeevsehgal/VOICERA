import os
import time
import json
import requests
from typing import List, Optional

from utils.logging import log_info, log_warning, log_error
from services.gemini_key_manager import gemini_key_manager


# Fallback overhead tokens per request when estimating budgets
_GEMINI_TOKEN_OVERHEAD = int(os.getenv("GEMINI_TOKEN_OVERHEAD", "32"))
_DEFAULT_TIMEOUT_S = float(os.getenv("GEMINI_REQUEST_TIMEOUT", "45"))


def _estimate_tokens(text: str) -> int:
    if not text:
        return 1
    words = len([w for w in text.split() if w])
    approx_chars = max(1, len(text))
    return max(1, max(words, approx_chars // 3))


def _build_generation_config(
    temperature: Optional[float],
    max_output_tokens: Optional[int],
    top_p: Optional[float],
    top_k: Optional[int],
) -> dict:
    cfg: dict = {}
    if temperature is not None:
        cfg["temperature"] = temperature
    if max_output_tokens is not None:
        cfg["maxOutputTokens"] = int(max_output_tokens)
    if top_p is not None:
        cfg["topP"] = top_p
    if top_k is not None:
        cfg["topK"] = top_k
    return cfg


# ---------------------------------------------
# Error mapping for Gemini API (aligns with docs)
# ---------------------------------------------

class GeminiAPIError(Exception):
    """Structured error for Gemini API failures.

    Captures the HTTP code, canonical status, raw message, a friendly description,
    and an actionable solution hint to align with Google Gemini error taxonomy.
    """

    def __init__(
        self,
        http_code: int,
        status: str,
        message: Optional[str] = None,
        description: Optional[str] = None,
        solution: Optional[str] = None,
        raw_text: Optional[str] = None,
    ) -> None:
        self.http_code = http_code
        self.status = status
        self.message = message or ""
        self.description = description or ""
        self.solution = solution or ""
        self.raw_text = raw_text or ""
        text = (
            f"Gemini API {http_code} {status}: {self.message or self.description}"
            + (f" | Solution: {self.solution}" if self.solution else "")
        )
        super().__init__(text)


_DEFAULT_STATUS_BY_HTTP = {
    400: "INVALID_ARGUMENT",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    429: "RESOURCE_EXHAUSTED",
    500: "INTERNAL",
    503: "UNAVAILABLE",
    504: "DEADLINE_EXCEEDED",
}

_STATUS_DOC = {
    (400, "INVALID_ARGUMENT"): {
        "description": "The request body is malformed.",
        "solution": "Check the API reference for request format, examples, and supported versions. Ensure there are no typos and all required fields are present.",
    },
    (400, "FAILED_PRECONDITION"): {
        "description": "Gemini API free tier is not available in your country or billing not enabled.",
        "solution": "Enable billing on your project in Google AI Studio or use a supported region.",
    },
    (403, "PERMISSION_DENIED"): {
        "description": "Your API key doesn't have the required permissions or you're using a tuned model without proper authentication.",
        "solution": "Verify the API key and its permissions. For tuned models, authenticate per the docs and ensure the key has access.",
    },
    (404, "NOT_FOUND"): {
        "description": "The requested resource wasn't found (e.g., referenced media is missing).",
        "solution": "Validate all request parameters and referenced resources for your API version.",
    },
    (429, "RESOURCE_EXHAUSTED"): {
        "description": "You've exceeded the rate or quota limit.",
        "solution": "Back off and retry respecting the model's rate limits, or request a quota increase.",
    },
    (500, "INTERNAL"): {
        "description": "An unexpected error occurred on Google's side, or your input context may be too long.",
        "solution": "Try reducing context size, switching to a different model variant, and retry later. Report persistent issues via Google AI Studio feedback.",
    },
    (503, "UNAVAILABLE"): {
        "description": "The service is temporarily overloaded or down.",
        "solution": "Retry after a delay or temporarily switch to another model variant.",
    },
    (504, "DEADLINE_EXCEEDED"): {
        "description": "The service couldn't finish processing within the deadline.",
        "solution": "Increase client timeout or reduce prompt/context size.",
    },
}


def _build_gemini_api_error(resp: requests.Response) -> GeminiAPIError:
    """Convert a Google error response to a structured GeminiAPIError."""
    http = resp.status_code
    raw_text = resp.text
    status = None
    message = None
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            status = err.get("status")
            message = err.get("message")
    except Exception:
        body = None

    if not status:
        status = _DEFAULT_STATUS_BY_HTTP.get(http, "UNKNOWN")

    doc = _STATUS_DOC.get((http, status)) or _STATUS_DOC.get((http, _DEFAULT_STATUS_BY_HTTP.get(http, "")))
    description = doc["description"] if doc else None
    solution = doc["solution"] if doc else None

    # Add helpful logging context
    log_error(
        "Gemini API error",
        "gemini_text_client",
        {
            "http_code": http,
            "status": status,
            "message": message,
            "description": description,
        },
    )

    return GeminiAPIError(http, status, message, description, solution, raw_text)


def generate_text(
    model_name: str,
    messages: List[str],
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    timeout_s: Optional[float] = None,
) -> str:
    """
    Generate text using Gemini REST API with multi-key rate-aware selection.

    Args:
      model_name: Gemini model (e.g., "gemini-1.5-flash")
      messages: One or more user messages (strings)
      system_prompt: Optional system instruction
      temperature, max_output_tokens, top_p, top_k: generation config
      timeout_s: request timeout seconds (default from env)

    Returns: response text from the first candidate
    """
    if not gemini_key_manager.has_keys():
        raise RuntimeError("No Gemini API keys configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

    # Estimate tokens (input only + overhead for simplicity)
    tokens = sum(_estimate_tokens(m) for m in messages) + _GEMINI_TOKEN_OVERHEAD

    # Build the payload
    contents = [
        {"role": "user", "parts": [{"text": m}]} for m in messages
    ]
    payload: dict = {
        "contents": contents,
        "generationConfig": _build_generation_config(temperature, max_output_tokens, top_p, top_k),
    }
    if system_prompt:
        payload["systemInstruction"] = {
            "role": "system",
            "parts": [{"text": system_prompt}],
        }

    last_err: Optional[Exception] = None
    timeout = timeout_s if timeout_s is not None else _DEFAULT_TIMEOUT_S

    # Modest retry loop mirroring embedding behavior
    base_delay = float(os.getenv("GENERATION_RETRY_BASE_DELAY", "0.5"))
    max_retries = int(os.getenv("GENERATION_MAX_RETRIES", "5"))

    def _is_retriable(http_code: int, status: Optional[str]) -> bool:
        if http_code == 429:
            return True
        if http_code in (500, 503, 504):
            return True
        # Unknown 5xx
        if 500 <= http_code <= 599:
            return True
        # Everything else (400/401/403/404 etc.) is not retriable by default
        return False

    for attempt in range(1, max_retries + 1):
        api_key = None
        try:
            api_key = gemini_key_manager.acquire(tokens, request_type="gen")
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            }
            log_info(
                f"Gemini generate (attempt {attempt}) model={model_name}",
                "gemini_text_client",
                {"attempt": attempt, "model": model_name, "msg_count": len(messages)},
            )
            try:
                resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
            except requests.Timeout as te:
                # Map client timeout to DEADLINE_EXCEEDED (504)
                if api_key:
                    gemini_key_manager.report_result(api_key, 504, None, status="DEADLINE_EXCEEDED")
                raise GeminiAPIError(
                    504,
                    "DEADLINE_EXCEEDED",
                    message=str(te),
                    description="The service couldn't finish processing within the client deadline.",
                    solution="Increase client timeout or reduce prompt/context size.",
                )
            except requests.ConnectionError as ce:
                # Map to UNAVAILABLE (503)
                if api_key:
                    gemini_key_manager.report_result(api_key, 503, None, status="UNAVAILABLE")
                raise GeminiAPIError(
                    503,
                    "UNAVAILABLE",
                    message=str(ce),
                    description="Network issue or service temporarily unavailable.",
                    solution="Retry after a short delay or switch to another model variant.",
                )
            except requests.RequestException as re:
                if api_key:
                    # Treat as INTERNAL transient by default
                    gemini_key_manager.report_result(api_key, 500, None, status="INTERNAL")
                raise GeminiAPIError(
                    500,
                    "INTERNAL",
                    message=str(re),
                    description="Unexpected client error during request.",
                    solution="Retry the request; if it persists, inspect client/network setup.",
                )

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                try:
                    ra = float(retry_after) if retry_after and str(retry_after).isdigit() else None
                except Exception:
                    ra = None
                gemini_key_manager.report_result(api_key, 429, ra, status="RESOURCE_EXHAUSTED")
                sleep_s = ra if ra is not None else base_delay * (2 ** (attempt - 1))
                log_warning(
                    f"Gemini generate 429. Sleeping {sleep_s:.2f}s",
                    "gemini_text_client",
                    {"sleep_time": sleep_s},
                )
                time.sleep(sleep_s)
                continue

            if resp.status_code >= 400:
                err = _build_gemini_api_error(resp)
                gemini_key_manager.report_result(api_key, resp.status_code, None, status=err.status)
                # If not retriable, raise immediately (bypass retry loop)
                if not _is_retriable(err.http_code, err.status):
                    raise err
                # Retriable errors fall-through to retry logic below
                raise err

            # Success
            gemini_key_manager.report_result(api_key, 200, None)
            data = resp.json()
            # Parse first candidate text
            text_out = _extract_text_from_candidates(data)
            if text_out is None:
                raise RuntimeError(f"Gemini generate: no text in response: {data}")
            return text_out
        except Exception as e:
            last_err = e
            # If it's a structured error and non-retriable, stop immediately
            if isinstance(e, GeminiAPIError) and not _is_retriable(getattr(e, "http_code", 0), getattr(e, "status", None)):
                log_error(
                    f"Non-retriable Gemini error: {e}",
                    "gemini_text_client",
                    {"attempt": attempt, "http_code": getattr(e, "http_code", None), "status": getattr(e, "status", None)},
                )
                raise
            sleep_s = base_delay * (2 ** (attempt - 1))
            log_warning(
                f"Gemini generate attempt {attempt} failed: {e}. Retrying in {sleep_s:.2f}s...",
                "gemini_text_client",
                {"attempt": attempt, "error": str(e), "sleep_time": sleep_s},
            )
            time.sleep(sleep_s)
        finally:
            api_key = None

    # Exhausted retries
    log_error(
        f"Failed Gemini generate after {max_retries} attempts: {last_err}",
        "gemini_text_client",
        {"max_retries": max_retries, "error": str(last_err) if last_err else None},
    )
    raise last_err  # type: ignore


def _extract_text_from_candidates(data: dict) -> Optional[str]:
    try:
        cands = data.get("candidates")
        if not cands or not isinstance(cands, list):
            return None
        cand0 = cands[0]
        content = cand0.get("content") if isinstance(cand0, dict) else None
        if not content or not isinstance(content, dict):
            return None
        parts = content.get("parts")
        if not parts or not isinstance(parts, list):
            return None
        texts: List[str] = []
        for p in parts:
            if isinstance(p, dict) and "text" in p and isinstance(p["text"], str):
                texts.append(p["text"])
        return "".join(texts) if texts else None
    except Exception:
        return None
