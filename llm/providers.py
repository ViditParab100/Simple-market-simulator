"""
Real LLM backends, all via stdlib urllib (no extra dependencies required).

- OllamaClient    — local, free, no API key.  Recommended default.
                    Install Ollama, then e.g. `ollama pull llama3.2`.
- OpenAIClient    — needs env var OPENAI_API_KEY.
- AnthropicClient — needs env var ANTHROPIC_API_KEY.

Each raises LLMError on any failure; LLMAgent catches it and falls back to rule
logic, so an unavailable model never crashes the simulation.
"""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.error

from .client import LLMClient


class LLMError(RuntimeError):
    pass


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
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
