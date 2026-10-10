"""Models wrap JSON in code fences or chatty preambles; dig the object out, then let the schema judge it."""
import json
import re

from pydantic import ValidationError

from llm.schema import TriageOut

FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class BadModelOutput(Exception):
    """The model's answer could not be parsed or failed the schema. str(e) is safe to send back to the model."""


def parse_triage(raw: str) -> TriageOut:
    text = raw.strip()
    m = FENCE.search(text)
    if m:
        text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise BadModelOutput("no JSON object found in the answer")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise BadModelOutput(f"invalid JSON: {e}") from e
    try:
        return TriageOut.model_validate(data)
    except ValidationError as e:
        raise BadModelOutput("; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from e
