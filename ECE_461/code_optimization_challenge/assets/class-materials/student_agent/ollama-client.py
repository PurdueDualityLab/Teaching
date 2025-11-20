"""
ollama-client.py

LLMClient implementation backed by a local Ollama server.

Supports:
    chat(prompt: str | List[Dict[str, Any]]) -> str
"""

from typing import Any, Dict, List, Union
from ollama import Client


class LLMClient:
    """
    Simple Ollama-based LLM client.

    Default model: qwen2.5-coder:7b
    """

    def __init__(self, model: str = "qwen2.5-coder:7b", host: str = "http://localhost:11434"):
        self._client = Client(host=host)
        self._model = model

    def chat(self, prompt: Union[str, List[Dict[str, Any]]]) -> str:
        """
        If `prompt` is a string → wrap as one user message.
        If `prompt` is a list → assume list of message dicts.
        """
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = prompt

        response = self._client.chat(
            model=self._model,
            messages=messages,
        )

        # Ollama returns: {"message": {"role": ..., "content": ...}}
        return response["message"]["content"]
