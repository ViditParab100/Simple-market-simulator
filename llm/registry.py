"""
Turn a string spec into an LLMClient.

Spec format:  "provider:model"  (model optional, sensible defaults applied)

    mock                            -> MockLLMClient (offline, deterministic)
    ollama:llama3.2                 -> local Ollama
    ollama:qwen2.5                  -> local Ollama, different model
    openai:gpt-4o-mini              -> OpenAI (needs OPENAI_API_KEY)
    anthropic:claude-haiku-4-5      -> Anthropic (needs ANTHROPIC_API_KEY)
    groq:llama-3.1-8b-instant       -> Groq (needs GROQ_API_KEY)  ← fast + free tier
    groq:llama-3.3-70b-versatile    -> Groq, larger model
    groq:llama-3.2-3b-preview       -> Groq, smallest/fastest model
"""
from __future__ import annotations
from .client import LLMClient, MockLLMClient
from .providers import OllamaClient, OpenAIClient, AnthropicClient, GroqClient

_DEFAULT_MODEL = {
    "ollama":    "llama3.2",
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "groq":      "llama-3.1-8b-instant",
}

_GROQ_TIMEOUT = 30.0  # Groq is fast; no need for the full 60 s


def make_client(spec: str, timeout: float = 60.0) -> LLMClient:
    spec = (spec or "").strip()
    if not spec or spec.lower() == "mock":
        return MockLLMClient()

    provider, _, model = spec.partition(":")
    provider = provider.lower().strip()
    model = model.strip() or _DEFAULT_MODEL.get(provider, "")

    if provider == "mock":
        return MockLLMClient()
    if provider == "ollama":
        return OllamaClient(model, timeout)
    if provider == "openai":
        return OpenAIClient(model, timeout)
    if provider == "anthropic":
        return AnthropicClient(model, timeout)
    if provider == "groq":
        return GroqClient(model, min(timeout, _GROQ_TIMEOUT))

    raise ValueError(
        f"Unknown LLM provider '{provider}'. "
        f"Use one of: mock, ollama, openai, anthropic, groq."
    )


def make_clients(specs: str, timeout: float = 60.0) -> list[LLMClient]:
    """Parse a comma-separated list of specs (for running multiple models)."""
    parts = [s for s in (specs or "").split(",") if s.strip()]
    if not parts:
        return [MockLLMClient()]
    return [make_client(p, timeout) for p in parts]
