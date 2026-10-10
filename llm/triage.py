"""The triage job: build prompt -> call model -> parse + validate -> repair once -> else 422 + quarantine."""
import json
import os
import time
from pathlib import Path

from fastapi import HTTPException

from llm import client
from llm.client import LLMError, LLMTimeout
from llm.parse import BadModelOutput, parse_triage
from llm.schema import TriageOut

PROMPT_VERSION = os.getenv("PROMPT_VERSION", "triage-v1")
ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "prompts"
QUARANTINE = ROOT / "logs" / "quarantine.jsonl"
STUB = TriageOut(category="chore", priority="normal", confidence=0.9, reason="Stub answer: no model was called.")

FALLBACK = TriageOut(category="other", priority="normal", confidence=0.0,
                     reason="AI triage is switched off; please triage this task by hand.")

REPAIR = ("Your previous answer was rejected for this reason: {error}. "
          "Return only corrected JSON matching the schema.")


def load_prompt() -> str:
    return (PROMPT_DIR / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def build_messages(text: str) -> list[dict]:
    # instructions in the system message; the user's content is JSON-encoded in the user message
    return [{"role": "system", "content": load_prompt()},
            {"role": "user", "content": json.dumps({"text": text})}]


def quarantine(text: str, raw_outputs: list[str], error: str) -> None:
    QUARANTINE.parent.mkdir(exist_ok=True)
    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "prompt_version": PROMPT_VERSION,
            "input": text, "raw_outputs": raw_outputs, "error": error}
    with QUARANTINE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def enabled() -> bool:
    return os.getenv("LLM_ENABLED", "true").strip().lower() not in ("false", "0", "no", "off")


def call_model(messages: list[dict], repair: bool = False) -> str:
    try:
        return client.complete(messages, prompt_version=PROMPT_VERSION, repair=repair).text
    except LLMTimeout as e:
        raise HTTPException(status_code=504, detail=f"The model took too long to answer ({e}). Try again later.")
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"The AI provider failed: {e}.")


def triage(text: str) -> TriageOut:
    if not enabled():  # kill switch: no model call, deterministic answer
        return FALLBACK
    if os.getenv("LLM_STUB") == "1":
        return STUB
    messages = build_messages(text)
    first = call_model(messages)
    try:
        return parse_triage(first)
    except BadModelOutput as e:
        error = str(e)
    # repair exactly once: same prompt + the broken output + the exact error
    messages += [{"role": "assistant", "content": first},
                 {"role": "user", "content": REPAIR.format(error=error)}]
    second = call_model(messages, repair=True)
    try:
        return parse_triage(second)
    except BadModelOutput as e:
        quarantine(text, [first, second], str(e))
        raise HTTPException(status_code=422, detail="The model did not return a valid triage result; it has been quarantined for review.")
