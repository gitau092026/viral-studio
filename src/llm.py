"""LLM access via Gemini's free REST API. Degrades gracefully when no key is set."""
from __future__ import annotations

import json
import re

import requests

from .settings import env

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def available() -> bool:
    return bool(env("GEMINI_API_KEY"))


def generate(prompt: str, system: str | None = None, model: str = "gemini-2.0-flash",
             temperature: float = 0.95, timeout: int = 60) -> str:
    """Return raw text from Gemini. Raises if no key or request fails."""
    key = env("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    resp = requests.post(
        _ENDPOINT.format(model=model),
        params={"key": key},
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response: {json.dumps(data)[:400]}") from e


def generate_json(prompt: str, system: str | None = None, **kw):
    """Ask the model for JSON and parse it, tolerating ```json fences and surrounding prose."""
    text = generate(prompt, system=system, **kw)
    return parse_json(text)


def parse_json(text: str):
    text = text.strip()
    # strip code fences
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # last resort: grab the outermost {...} or [...]
        m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        raise
