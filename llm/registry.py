"""
Turn a string spec into an LLMClient.

Spec format:  "provider:model"  (model optional, sensible defaults applied)

    mock                       -> MockLLMClient (offline, deterministic)
    ollama:llama3.2            -> local Ollama
    ollama:qwen2.5             -> local Ollama, different model
    openai:gpt-4o-mini         -> OpenAI (needs OPENAI_API_KEY)
    anthropic:claude-haiku-4-5 -> Anthropic (needs ANTHROPIC_API_KEY)
"""
from __future__ import annotations
from .client import LLMClient, MockLLMClient
from .providers import OllamaClient, OpenAIClient, AnthropicClient

_DEFAULT_MODEL = {
    "ollama":    "llama3.2",
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
}


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

    raise ValueError(
        f"Unknown LLM provider '{provider}'. "
        f"Use one of: mock, ollama, openai, anthropic."
    )


def make_clients(specs: str, timeout: float = 60.0) -> list[LLMClient]:
    """Parse a comma-separated list of specs (for running multiple models)."""
    parts = [s for s in (specs or "").split(",") if s.strip()]
    if not parts:
        return [MockLLMClient()]
    return [make_client(p, timeout) for p in parts]
