from __future__ import annotations

import json
import pathlib
from jsonschema import Draft202012Validator

_schema = None


def load_event_schema():
    global _schema
    if _schema is None:
        schema_path = pathlib.Path(__file__).parent.parent / "models" / "event_schema.json"
        _schema = json.loads(schema_path.read_text())
    return _schema


def validate_event_json(data: dict) -> None:
    schema = load_event_schema()
    Draft202012Validator(schema).validate(data)
