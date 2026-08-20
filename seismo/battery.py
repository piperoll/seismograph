"""Probe battery loading and canonical hashing.

The battery is PRIVATE - it never enters the public repo (see .gitignore).
What is public is its sha256, committed with every reading: proof the battery
was unchanged across the series without revealing it (charter decision 2).

Battery file format (JSON):
    {
      "battery": "canary",
      "version": "0.1",
      "probes": [
        {
          "id": "fmt-json-001",
          "dimension": "structured-output",
          "system": null,                      # optional system prompt
          "prompt": [{"role": "user", "content": "..."}],
          "params": {"max_tokens": 200, "temperature": 0},
          "samples": 3,
          "grader": {"type": "json_valid"}     # see grade.py for types
        }
      ]
    }
"""

import hashlib
import json

DIMENSIONS = {
    "structured-output",
    "tool-call",
    "instruction-following",
    "refusal-boundary",
    "capability",
    "sycophancy",
    "verbosity",
}

REQUIRED_PROBE_KEYS = {"id", "dimension", "prompt", "samples", "grader"}


def canonical_sha256(obj):
    """Hash of the parsed structure, not the file bytes - stable under
    whitespace/key-order edits so a reformat never masquerades as a battery
    change (and a battery change can never hide as a reformat)."""
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def load_battery(path):
    with open(path, encoding="utf-8") as f:
        battery = json.load(f)
    errors = validate_battery(battery)
    if errors:
        raise ValueError("invalid battery:\n" + "\n".join(errors))
    battery["_sha256"] = canonical_sha256(
        {k: v for k, v in battery.items() if not k.startswith("_")})
    return battery


def validate_battery(battery):
    errors = []
    for key in ("battery", "version", "probes"):
        if key not in battery:
            errors.append(f"missing top-level key: {key}")
    seen = set()
    for i, probe in enumerate(battery.get("probes", [])):
        where = f"probe[{i}] ({probe.get('id', '?')})"
        missing = REQUIRED_PROBE_KEYS - probe.keys()
        if missing:
            errors.append(f"{where}: missing {sorted(missing)}")
            continue
        if probe["id"] in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(probe["id"])
        if probe["dimension"] not in DIMENSIONS:
            errors.append(f"{where}: unknown dimension {probe['dimension']!r}")
        if not isinstance(probe["prompt"], list) or not probe["prompt"]:
            errors.append(f"{where}: prompt must be a non-empty message list")
        else:
            for m in probe["prompt"]:
                if not isinstance(m, dict) or "role" not in m or "content" not in m:
                    errors.append(f"{where}: malformed message")
                    break
        if not isinstance(probe["samples"], int) or probe["samples"] < 1:
            errors.append(f"{where}: samples must be a positive int")
        if not isinstance(probe["grader"], dict) or "type" not in probe["grader"]:
            errors.append(f"{where}: grader must be a dict with a type")
    return errors
