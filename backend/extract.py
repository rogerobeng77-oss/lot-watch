"""Nano reads one MAUDE narrative and recovers the facts the form fields drop.

This is the non-obvious part of Lot Watch: the device, the lot and the failure
mode that matter are often only in the free text (a stapler death filed under the
instrument code with the recalled reload named only in section D10). A structured
search never sees them; a model that reads the narrative does.

Uses Nemotron Nano with reasoning_effort="low" — a cheap classify/extract call,
strict JSON out. Kept behind the app's one "Run it" button so a visitor's click,
not a background loop, is what spends a token.
"""

from __future__ import annotations

import json

from nemotron import NANO, think

SCHEMA = {
    "failure_mode": "one of: no staples formed | incomplete staple line | uncut or retained washer (circular stapler) | lockout / would not fire | misfire | staple/fragment left | other | not stated",
    "tissue": "the tissue or vessel operated on (e.g. pulmonary artery, bowel, stomach, lung), or 'not stated'",
    "device_in_text": "any device model/catalog/product number named in the narrative, even if it differs from the report's device field; '' if none",
    "lot_in_text": "any lot number named in the narrative; '' if none",
    "harm": "one of: death | serious injury | malfunction only | not stated",
    "device_returned": "yes | no | not stated — was the device returned to the manufacturer for analysis",
    "one_line": "one plain sentence, <=22 words, saying what happened",
}

SYS = (
    "You read a single FDA MAUDE medical-device report narrative and return STRICT JSON only. "
    "Extract only what the text supports; never invent a number, lot, or device. "
    "If the text does not say, use 'not stated' (or '' for the free-text id fields). "
    "Return a JSON object with exactly these keys: "
    + ", ".join(SCHEMA.keys()) + "."
)


def extract(narrative: str, *, model: str = NANO) -> dict:
    """Return the structured facts Nano reads out of one narrative."""
    text = narrative.strip()
    if len(text) > 9000:
        text = text[:9000]
    prompt = (
        "Schema (value = how to fill it):\n"
        + json.dumps(SCHEMA, indent=2)
        + "\n\nReport narrative:\n\"\"\"\n" + text + "\n\"\"\"\n\n"
        "Return the JSON object now."
    )
    msg = think(
        [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}],
        model=model, reasoning_effort="low", max_tokens=4096, json_out=True,
    )
    # json_out=True makes think() return the parsed object
    out = msg if isinstance(msg, dict) else {}
    # keep only the known keys, in order
    return {k: out.get(k, "not stated") for k in SCHEMA}


if __name__ == "__main__":
    import corpus
    rec = corpus.find_report("intuitive_deaths", "2955842-2026-01596")
    print(json.dumps(extract(rec["narrative"]), indent=2))
