"""LLM adapter: one chat() interface over any OpenAI-compatible endpoint. BYOK.

No vendor SDK. Plain HTTPS + JSON covers Anthropic, OpenAI, Gemini, Ollama,
or anything speaking /v1/chat/completions. Single pass; verification is local.

Env: MODEL, BASE_URL, API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY).
Model families handled: claude-* (Anthropic messages API), gpt-*/o* (OpenAI),
anything else via BASE_URL (Gemini/Ollama/OpenAI-compatible).
"""
from __future__ import annotations

import json
import os
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class LMError(RuntimeError):
    pass

# Reasoning models: no response_format, no system role, completion-token param.
_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def is_reasoning_model(model: str) -> bool:
    m = model.lower()
    return m.startswith(_REASONING_PREFIXES)


def _config(model: str | None = None) -> tuple[str, str, str]:
    """Resolve (base_url, api_key, model). Anthropic needs its own base URL + headers."""
    model = model or os.getenv("MODEL", "claude-sonnet-4-6")
    base_url = os.getenv("BASE_URL", "").rstrip("/")
    api_key = (os.getenv("API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
               or os.getenv("ANTHROPIC_API_KEY", ""))
    if not base_url:
        base_url = ("https://api.anthropic.com/v1" if model.startswith("claude")
                    else "https://api.openai.com/v1")
    return base_url, api_key, model


def _anthropic_payload(model: str, system: str, user: str, schema_hint: str) -> dict:
    return {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user",
                      "content": f"{user}\n\nRespond with JSON matching this shape:\n{schema_hint}"}],
    }


def _openai_payload(model: str, system: str, user: str, schema_hint: str) -> dict:
    content = f"{user}\n\nRespond with JSON matching this shape:\n{schema_hint}"
    if is_reasoning_model(model):
        # o-series: user role only, no response_format, completion tokens.
        return {"model": model,
                "max_completion_tokens": 4096,
                "messages": [{"role": "user", "content": f"{system}\n\n{content}"}]}
    return {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }


def _strip_fences(text: str) -> str:
    """Models often wrap JSON in ```json fences despite instructions. Unwrap."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rsplit("```", 1):
            t = t.rsplit("```", 1)[0]
    return t.strip()


def chat(system: str, user: str, schema_hint: str = '{"fields": {}}',
         model: str | None = None, timeout: int = 120) -> dict:
    """Call the configured model, return parsed JSON. Raises LMError on failure."""
    base_url, api_key, resolved = _config(model)
    if not api_key:
        raise LMError("No API key: set API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY).")
    is_anthropic = "anthropic.com" in base_url
    payload = (_anthropic_payload(resolved, system, user, schema_hint) if is_anthropic
               else _openai_payload(resolved, system, user, schema_hint))
    url = base_url + ("/messages" if is_anthropic else "/chat/completions")
    headers = {"Content-Type": "application/json"}
    if is_anthropic:
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except Exception as e:
        raise LMError(f"LLM request failed: {e}")
    try:
        text = (body["content"][0]["text"] if is_anthropic
                else body["choices"][0]["message"]["content"])
        return json.loads(_strip_fences(text))
    except Exception as e:
        raise LMError(f"Could not parse LLM JSON: {e}")
