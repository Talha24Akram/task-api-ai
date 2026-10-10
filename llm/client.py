"""Thin wrapper over the OpenAI-compatible client. Provider = three env vars (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL).

Policy (written down on purpose, silent SDK defaults are how you make six calls when you think you made one):
- timeout: 30 s per attempt (SDK default is 10 minutes).
- retries: the SDK's own retries are OFF (max_retries=0); this module retries instead, only on
  timeouts, connection drops, 429 and 5xx. Never on 400/401/403/404, a bad key stays a bad key.
- backoff: 1 s, 2 s, 4 s plus up to 0.5 s of jitter; a 429 with Retry-After obeys the header instead.
"""
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

import openai
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("llm")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))  # seconds per attempt
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))  # retries after the first attempt
MAX_RETRY_AFTER = 30.0
CALL_LOG = Path(__file__).resolve().parent.parent / "logs" / "llm-calls.jsonl"
sleep = time.sleep  # swapped out in tests


class LLMTimeout(Exception):
    """Every attempt timed out."""


class LLMError(Exception):
    """The provider refused or failed; message is safe to show, details are in the call log."""


@dataclass
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    retries: int = 0


def _client() -> openai.OpenAI:
    return openai.OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"],
                         timeout=TIMEOUT, max_retries=0)


def _write_log(entry: dict) -> None:
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}
    log.info("llm_call %s", json.dumps(entry))
    CALL_LOG.parent.mkdir(exist_ok=True)
    with CALL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _delay(attempt: int, err: Exception) -> float:
    retry_after = getattr(getattr(err, "response", None), "headers", {}).get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), MAX_RETRY_AFTER)
        except ValueError:
            pass
    return 2 ** attempt + random.uniform(0, 0.5)  # 1, 2, 4 seconds + jitter


def complete(messages: list[dict], *, prompt_version: str = "", repair: bool = False) -> Completion:
    model = os.environ["LLM_MODEL"]
    t0 = time.monotonic()
    base = {"prompt_version": prompt_version, "model": model, "repair": repair}
    for attempt in range(MAX_RETRIES + 1):
        try:
            res = _client().chat.completions.create(model=model, messages=messages, temperature=0, max_tokens=1000)
            usage = res.usage
            done = Completion(
                text=res.choices[0].message.content or "",
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                duration_ms=int((time.monotonic() - t0) * 1000), retries=attempt)
            _write_log({**base, "status": "ok", "input_tokens": done.input_tokens,
                        "output_tokens": done.output_tokens, "duration_ms": done.duration_ms, "retries": attempt})
            return done
        except (openai.APITimeoutError, openai.APIConnectionError, openai.APIStatusError) as e:
            status = getattr(e, "status_code", None)
            retryable = status is None or status == 429 or status >= 500
            if retryable and attempt < MAX_RETRIES:
                sleep(_delay(attempt, e))
                continue
            _write_log({**base, "status": "error", "http_status": status, "error": type(e).__name__,
                        "duration_ms": int((time.monotonic() - t0) * 1000), "retries": attempt})
            if isinstance(e, openai.APITimeoutError):
                raise LLMTimeout(f"no answer within {TIMEOUT:g}s") from e
            raise LLMError(f"provider error ({status or type(e).__name__})") from e
    raise AssertionError("unreachable")
