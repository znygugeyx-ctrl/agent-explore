"""Built-in LLM providers. Import this module to register them."""

from .bedrock import BedrockProvider
from .openai_compat import OpenAICompatProvider

__all__ = ["BedrockProvider", "OpenAICompatProvider"]
