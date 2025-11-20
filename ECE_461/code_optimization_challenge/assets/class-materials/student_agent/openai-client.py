"""
openai-client.py

LLMClient implementation for OpenAI Chat Completions API.

Reads token from environment variable:
    ECE30861_OPENAI_TOKEN

Supports:
    chat(prompt: str | List[Dict[str, Any]]) -> str
"""

import os
from typing import Any, Dict, List, Union
from openai import OpenAI


class LLMClient:
    """
    OpenAI-backed LLM client.

    Default model: o3-mini
    """

    def __init__(self, model: str = "o3-mini"):
        api_key = os.getenv("ECE30861_OPENAI_TOKEN")
        if not api_key:
            raise RuntimeError(
                "Missing environment variable ECE30861_OPENAI_TOKEN. "
                "Set it to your OpenAI API key."
            )

        self._client = OpenAI(api_key=api_key)
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

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )

        choice = response.choices[0]
        content = choice.message.content or ""

        # Sometimes OpenAI returns content as a list of text blocks
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )

        return content
