"""Thin wrapper over the OpenAI-compatible client. Provider = three env vars."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))  # seconds; the SDK default is 10 minutes


@dataclass
class Completion:
    text: str


def _client() -> OpenAI:
    return OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"],
                  timeout=TIMEOUT, max_retries=0)


def complete(messages: list[dict]) -> Completion:
    res = _client().chat.completions.create(
        model=os.environ["LLM_MODEL"], messages=messages, temperature=0, max_tokens=1000)
    return Completion(text=res.choices[0].message.content or "")
