import os
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class LLMProvider(ABC):
    """Abstract base provider for LLM generation."""
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str, max_tokens: int = 500, timeout: int = 20) -> str:
        pass

class MockProvider(LLMProvider):
    """
    Mock provider that never fabricates answers.
    Used for safe offline testing and zero-cost local evaluation.
    """
    def generate(self, prompt: str, system_prompt: str, max_tokens: int = 500, timeout: int = 20) -> str:
        # MockProvider strictly never fabricates text.
        # It signals provider_unavailable so generator falls back to deterministic extractive mode.
        raise RuntimeError("MockProvider active: no real LLM endpoint configured.")

class OpenAIProvider(LLMProvider):
    """OpenAI API Provider with lazy import."""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")

    def generate(self, prompt: str, system_prompt: str, max_tokens: int = 500, timeout: int = 20) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set.")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, timeout=timeout)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.0
            )
            return response.choices[0].message.content.strip()
        except ImportError:
            raise ImportError("openai package not installed. Install via pip install openai.")
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise

class AnthropicProvider(LLMProvider):
    """Anthropic Claude API Provider with lazy import."""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL", "claude-3-haiku-20240307")

    def generate(self, prompt: str, system_prompt: str, max_tokens: int = 500, timeout: int = 20) -> str:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set.")
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key, timeout=timeout)
            response = client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.0
            )
            return response.content[0].text.strip()
        except ImportError:
            raise ImportError("anthropic package not installed. Install via pip install anthropic.")
        except Exception as e:
            logger.error(f"Anthropic generation failed: {e}")
            raise

def get_provider() -> LLMProvider:
    """Factory to get configured LLM provider from environment."""
    provider_name = os.environ.get("LLM_PROVIDER", "mock").lower()
    if provider_name == "openai":
        return OpenAIProvider()
    elif provider_name == "anthropic":
        return AnthropicProvider()
    else:
        return MockProvider()
