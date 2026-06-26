"""
Real LLM backends, all via stdlib urllib (no extra dependencies required).

- OllamaClient    — local, free, no API key.  Recommended default.
                    Install Ollama, then e.g. `ollama pull llama3.2`.
- OpenAIClient    — needs env var OPENAI_API_KEY.
- AnthropicClient — needs env var ANTHROPIC_API_KEY.
- GroqClient      — needs env var GROQ_API_KEY.  OpenAI-compatible API,
                    very fast inference.  Free tier available at console.groq.com.
                    Good models: llama-3.1-8b-instant, llama-3.3-70b-versatile,
                                 gemma2-9b-it, mixtral-8x7b-32768

Each raises LLMError on any failure; LLMAgent catches it and falls back to rule
logic, so an unavailable model never crashes the simulation.
"""
from __future__ import annotations
import json
import os
import time
import urllib.request
import urllib.error

from .client import LLMClient


class LLMError(RuntimeError):
    pass


class _RateLimitError(LLMError):
    """HTTP 429 with optional Retry-After seconds."""
    def __init__(self, msg: str, retry_after: float = 5.0):
        super().__init__(msg)
        self.retry_after = retry_after


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        if e.code == 429:
            try:
                retry_after = float(e.headers.get("Retry-After", 5))
            except (TypeError, ValueError):
                retry_after = 5.0
            raise _RateLimitError(f"HTTP 429: {body}", retry_after) from e
        raise LLMError(f"HTTP {e.code}: {body}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(str(e)) from e
    except (ValueError, KeyError) as e:
        raise LLMError(f"bad response: {e}") from e


class OllamaClient(LLMClient):
    """Local Ollama server (default http://localhost:11434)."""

    def __init__(self, model: str = "llama3.2", timeout: float = 60.0,
                 host: str | None = None):
        self.model   = model
        self.timeout = timeout
        self.host    = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.name    = f"ollama:{model}"

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 200},
        }
        out = _post_json(f"{self.host}/api/chat", payload,
                         {"Content-Type": "application/json"}, self.timeout)
        try:
            return out["message"]["content"]
        except (KeyError, TypeError) as e:
            raise LLMError(f"unexpected Ollama response: {e}") from e


class OpenAIClient(LLMClient):
    """OpenAI chat completions. Requires OPENAI_API_KEY."""

    def __init__(self, model: str = "gpt-4o-mini", timeout: float = 60.0):
        self.model   = model
        self.timeout = timeout
        self.name    = f"openai:{model}"

    def complete(self, system: str, user: str) -> str:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise LLMError("OPENAI_API_KEY not set")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "temperature": 0.7,
            "max_tokens": 200,
        }
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {key}"}
        out = _post_json("https://api.openai.com/v1/chat/completions",
                         payload, headers, self.timeout)
        try:
            return out["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"unexpected OpenAI response: {e}") from e


class AnthropicClient(LLMClient):
    """Anthropic Messages API. Requires ANTHROPIC_API_KEY."""

    def __init__(self, model: str = "claude-haiku-4-5", timeout: float = 60.0):
        self.model   = model
        self.timeout = timeout
        self.name    = f"anthropic:{model}"

    def complete(self, system: str, user: str) -> str:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("ANTHROPIC_API_KEY not set")
        payload = {
            "model": self.model,
            "max_tokens": 200,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }
        out = _post_json("https://api.anthropic.com/v1/messages",
                         payload, headers, self.timeout)
        try:
            return out["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"unexpected Anthropic response: {e}") from e


class GroqClient(LLMClient):
    """
    Groq cloud inference (OpenAI-compatible API). Requires GROQ_API_KEY.

    Free tier available at https://console.groq.com
    Fast models: llama-3.1-8b-instant, llama-3.3-70b-versatile, llama-3.2-3b-preview
    """

    _BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, model: str = "llama-3.1-8b-instant", timeout: float = 30.0):
        self.model   = model
        self.timeout = timeout
        self.name    = f"groq:{model}"

    def complete(self, system: str, user: str) -> str:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise LLMError("GROQ_API_KEY not set")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "temperature": 0.7,
            "max_tokens": 120,  # JSON reply is compact; keep costs low
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "python-groq/0.9.0",  # Cloudflare blocks bare urllib UA
        }
        for attempt in range(2):
            try:
                out = _post_json(self._BASE_URL, payload, headers, self.timeout)
                try:
                    return out["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    raise LLMError(f"unexpected Groq response: {e}") from e
            except _RateLimitError as e:
                if attempt == 0:
                    wait = min(e.retry_after, 10.0)  # cap at 10s; don't stall the sim
                    time.sleep(wait)
                else:
                    raise  # second failure → fallback kicks in
        raise LLMError("unreachable")
