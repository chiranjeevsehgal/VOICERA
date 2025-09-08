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
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                try:
                    ra = float(retry_after) if retry_after and str(retry_after).isdigit() else None
                except Exception:
                    ra = None
                gemini_key_manager.report_result(api_key, 429, ra)
                sleep_s = ra if ra is not None else base_delay * (2 ** (attempt - 1))
                log_warning(
                    f"Gemini generate 429. Sleeping {sleep_s:.2f}s",
                    "gemini_text_client",
                    {"sleep_time": sleep_s},
                )
                time.sleep(sleep_s)
                continue

            if resp.status_code >= 400:
                gemini_key_manager.report_result(api_key, resp.status_code, None)
                raise RuntimeError(f"Gemini generate HTTP {resp.status_code}: {resp.text}")

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
