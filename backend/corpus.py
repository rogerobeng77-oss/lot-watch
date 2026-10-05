"""Load and normalize the FDA MAUDE records Lot Watch reads.

Every record here is a real openFDA device/event report (CC0), downloaded during
research and shipped with the app in corpus_data/. openFDA reports are unvalidated
and carry no denominator, so this module never computes a rate — it only reads what
the reports say, with the free-text narrative kept intact because that is where the
device, lot and failure the structured fields drop actually live.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "corpus_data"

# The datasets the app works over, each a real openFDA pull saved in research/.
DATASETS = {
    "sureform": "maude-intuitive-sureform30-48230M.json",
    "intuitive_deaths": "maude-intuitive-stapler-deaths-2024-2026.json",
    "vasecr35": "maude-ethicon-echelon-VASECR35.json",
    "cdh29a": "maude-ethicon-circular-CDH29A-sample300.json",
    "gag_gdw_deaths": "maude-GAG-GDW-deaths-2024-2025.json",
}


def _as_date(yyyymmdd: str) -> str:
    """openFDA's YYYYMMDD -> ISO, or '' if unparseable."""
    if not yyyymmdd or len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        return ""
    try:
        return date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8])).isoformat()
    except ValueError:
        return ""


def narrative_of(rec: dict) -> str:
    """Join every free-text block in a report into one string, in order."""
    out = []
    for t in rec.get("mdr_text", []) or []:
        txt = (t.get("text") or "").strip()
        if txt:
            out.append(txt)
    return "\n".join(out)


def normalize(rec: dict) -> dict:
    """One MAUDE report -> the fields Lot Watch displays and reasons over."""
    dev = (rec.get("device") or [{}])[0]
    pats = rec.get("patient") or []
    problems: list[str] = []
    for p in pats:
        for pp in p.get("patient_problems", []) or []:
            if pp and pp not in problems:
                problems.append(pp)
    ofda = dev.get("openfda", {}) or {}
    return {
        "report_number": rec.get("report_number", ""),
        "date_received": _as_date(rec.get("date_received", "")),
        "event_type": rec.get("event_type", ""),
        "brand": (dev.get("brand_name") or "").strip(),
        "generic": (dev.get("generic_name") or "").strip(),
        "manufacturer": (dev.get("manufacturer_d_name") or rec.get("manufacturer_name") or "").strip(),
        "model_number": (dev.get("model_number") or "").strip(),
        "catalog_number": (dev.get("catalog_number") or "").strip(),
        "lot_number": (dev.get("lot_number") or "").strip(),
        "product_code": (dev.get("device_report_product_code") or "").strip(),
        "device_returned": (dev.get("device_availability") or "").strip(),
        "device_class": ofda.get("device_class", ""),
        "regulation_number": ofda.get("regulation_number", ""),
        "patient_problems": problems,
        "product_problems": rec.get("product_problems", []) or [],
        "narrative": narrative_of(rec),
    }


@lru_cache(maxsize=None)
def load(name: str) -> list[dict]:
    """Normalized records for a named dataset (cached)."""
    path = DATA / DATASETS[name]
    raw = json.loads(path.read_text())
    return [normalize(r) for r in raw.get("results", [])]


@lru_cache(maxsize=None)
def counts_by_year() -> dict:
    return json.loads((DATA / "counts-by-year-GAG-GDW.json").read_text())


@lru_cache(maxsize=None)
def event_type_counts() -> dict:
    """Death/Injury/Malfunction totals for the stapler code (GAG) and staple code (GDW)."""
    def flat(fn: str) -> dict:
        res = json.loads((DATA / fn).read_text()).get("results", [])
        return {r["term"]: r["count"] for r in res if r.get("term")}
    return {"GAG": flat("counts-eventtype-GAG.json"), "GDW": flat("counts-eventtype-GDW.json")}


def find_report(name: str, report_number: str) -> dict | None:
    for r in load(name):
        if r["report_number"] == report_number:
            return r
    return None


if __name__ == "__main__":
    for k in DATASETS:
        recs = load(k)
        deaths = sum(1 for r in recs if r["event_type"] == "Death")
        print(f"{k:16} {len(recs):4} records, {deaths:3} deaths")
    print("event-type counts:", event_type_counts())
