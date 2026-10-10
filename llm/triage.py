"""The triage job. Stage 2: prompt file + model call; the raw answer is returned for inspection only."""
import json
import os
from pathlib import Path

from llm import client
from llm.schema import TriageOut

PROMPT_VERSION = os.getenv("PROMPT_VERSION", "triage-v1")
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
STUB = TriageOut(category="chore", priority="normal", confidence=0.9, reason="Stub answer: no model was called.")


def load_prompt() -> str:
    return (PROMPT_DIR / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def build_messages(text: str) -> list[dict]:
    # instructions in the system message; the user's content is JSON-encoded in the user message
    return [{"role": "system", "content": load_prompt()},
            {"role": "user", "content": json.dumps({"text": text})}]


def triage(text: str):
    if os.getenv("LLM_STUB") == "1":
        return STUB
    return {"model_text": client.complete(build_messages(text)).text}  # temporary, replaced in Stage 3
