"""The triage job. Stage 1: stub mode only, the contract exists before the model does."""
import os

from fastapi import HTTPException

from llm.schema import TriageOut

STUB = TriageOut(category="chore", priority="normal", confidence=0.9, reason="Stub answer: no model was called.")


def triage(text: str) -> TriageOut:
    if os.getenv("LLM_STUB") == "1":
        return STUB
    raise HTTPException(status_code=503, detail="Model not wired up yet (set LLM_STUB=1)")
