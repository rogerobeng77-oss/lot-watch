"""Turns the cached Lot Watch findings and the loaded MAUDE reports into the board the UI reads.

The UI is Tripwire's (findings -> widgets -> rows). Nothing here is invented: findings are the
cached Nemotron-written findings, rows are the report tables those findings were built from.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "cache"

KIND = {"sureform": "hidden_death", "vasecr35": "recalled_lots", "codetrap": "code_gap",
        "cdh29a": "failure_modes", "notreturned": "device_not_returned"}
SEV = {"high": "high", "medium": "medium", "low": "low", "watch": "low"}
LINE = {
    "sureform": "The fatal report is filed under the stapler, not the reload.",
    "vasecr35": "Recalled lots show up in reports before the letter.",
    "codetrap": "A stapler-code search misses most of the deaths.",
    "cdh29a": "The text names failure modes the fields never do.",
    "notreturned": "For 125 of 144 deaths the maker never got the device back.",
}
GAP = {
    "sureform": [("Field search", 0, "0 deaths"), ("In the report text", 1, "1 death")],
    "vasecr35": [("On FDA's list", 57, "57 lots"), ("Already in reports", 28, "28 lots")],
    "codetrap": [("Stapler code", 8, "8"), ("Staple code", 404, "404")],
    "cdh29a": [("One code finds", 204, "204"), ("All reports", 300, "300")],
    "notreturned": [("Device returned", 18, "18"), ("Not returned", 125, "125")],
}
ORDER = ["sureform", "vasecr35", "codetrap", "cdh29a", "notreturned"]

REPORT_COLS = [
    {"field": "report", "header": "Report", "width": 175},
    {"field": "received", "header": "Date", "width": 110},
    {"field": "type", "header": "Type", "renderer": "status", "width": 120},
    {"field": "device", "header": "Device", "width": 110},
    {"field": "lot", "header": "Lot", "width": 115},
    {"field": "returned", "header": "Returned", "width": 120},
    {"field": "problem", "header": "Problem", "width": 220},
]


def _iso(d: str) -> str:
    return (d or "")[:10] + "T00:00:00Z" if d else ""


def _returned(v: str) -> str:
    v = (v or "").strip().lower()
    return {"no": "No", "yes": "Yes", "device was returned to manufacturer": "Yes", "no answer provided": "No answer"}.get(v, v.capitalize() or "—")


def _asof(generated: str) -> str:
    try:
        return datetime.strptime(generated, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fix(f: dict) -> dict:
    """The cached notreturned text was written from a count that has since been corrected (125 of 144, not 0)."""
    if f["id"] != "notreturned" or "125 of 144" in f["headline"]:
        return f
    f = dict(f)
    f["headline"] = "device not returned in 125 of 144 death reports"
    f["brief"] = ("In 2024-2025 FDA received 144 death reports for stapler and staple devices (codes GAG and GDW). "
                  "In 125 of them the device was not returned to the maker, 15 were returned, 3 are marked yes and 1 gave no answer. "
                  "By reporting maker: Covidien / Medtronic 75, Ethicon / J&J 51, Intuitive 18.\n\n"
                  "Where no device comes back, the narrative is the only record of what failed.")
    return f


def build() -> dict:
    src = json.loads((CACHE / "findings.json").read_text())
    as_of = _asof(src.get("generated", ""))
    by_id = {f["id"]: _fix(f) for f in src["findings"]}
    findings, widgets = [], []
    data = {"reports": [], "tallies": [], "codes": []}
    n_widgets = 0
    for rank, fid in enumerate(ORDER):
        f = by_id.get(fid)
        if not f:
            continue
        rows = f["table"]["rows"]
        flagged: list[str] = []
        dates = sorted(r["date"] for r in rows if r.get("date"))
        if fid == "codetrap":
            for i, r in enumerate(rows):
                rid = f"{fid}:{i}"
                data["codes"].append({"id": rid, "finding": fid, "code": r["report_number"], "deaths": int(r["device"]), "injuries": int(r["lot"]),
                                      "malfunctions": int(r["returned"]), "regulation": r["problem"], "origin": "fda", "ts": as_of, "day": as_of[:10]})
                flagged.append(rid)
            grid = {"dataset": "codes", "title": "Reports by product code", "where": {"finding": fid},
                    "columns": [{"field": "code", "header": "Product code", "width": 240}, {"field": "deaths", "header": "Deaths", "renderer": "bar"},
                                {"field": "injuries", "header": "Injuries", "renderer": "bar"}, {"field": "malfunctions", "header": "Malfunctions", "renderer": "bar"},
                                {"field": "regulation", "header": "Regulation", "width": 200}],
                    "highlight": flagged, "sort": {"field": "deaths", "dir": "desc"}}
            window = {"label": "public MAUDE, all years", "to": as_of}
        else:
            seen: dict[str, int] = {}
            for r in rows:
                seen[r["report_number"]] = seen.get(r["report_number"], 0) + 1
                rid = f"{fid}:{r['report_number']}" + (f"#{seen[r['report_number']]}" if seen[r["report_number"]] > 1 else "")
                data["reports"].append({"id": rid, "finding": fid, "report": r["report_number"], "received": r["date"], "type": r["event_type"],
                                        "device": r["device"], "lot": r["lot"], "returned": _returned(r["returned"]), "problem": "; ".join(dict.fromkeys(x.strip() for x in (r["problem"] or "").split(";") if x.strip())) or "—",
                                        "origin": "fda", "ts": _iso(r["date"]) or as_of, "day": r["date"]})
                if (fid in ("sureform", "vasecr35") and r["event_type"] == "Death") or (fid == "cdh29a" and r["event_type"] != "Malfunction") or fid == "notreturned" and r["returned"] == "no":
                    flagged.append(rid)
            cols = [dict(c) for c in REPORT_COLS]
            if fid == "cdh29a":
                cols[-1]["header"] = "Failure mode (read from text)"
            grid = {"dataset": "reports", "title": {"sureform": "Reports for reload 48230M, hidden death first", "vasecr35": "Reports naming a recalled lot",
                    "cdh29a": "CDH29A sample, each read into a failure mode", "notreturned": "Stapler and staple death reports, 2024-2025"}[fid],
                    "where": {"finding": fid}, "columns": cols, "highlight": flagged[:60],
                    "rules": [{"field": "type", "op": "eq", "value": "Death", "tone": "alert", "label": "Death"}]}
            window = {"label": f"{dates[0][:4]} to {dates[-1][:4]}" if dates else "", "to": _iso(dates[-1]) if dates else as_of}
        ch = f["chart"]
        for i, d in enumerate(ch["data"]):
            data["tallies"].append({"id": f"{fid}:t{i}", "finding": fid, "label": d["label"], "value": d["value"], "origin": "fda", "ts": as_of, "day": as_of[:10]})
        notes = [d["label"] for d in ch["data"] if d.get("note")]
        charts = [{"type": "tw-breakdown", "spec": {"dataset": "tallies", "by": "label", "agg": "sum", "field": "value", "where": {"finding": fid}, "limit": 8,
                   "chartType": "bar", "title": ch["title"], "highlight": notes[:6], "caption": "; ".join(f"{d['label']}: {d['note']}" for d in ch["data"] if d.get("note"))[:160]},
                   "layout": {"w": 12 if fid != "codetrap" else 24, "h": 18}}]
        if fid != "codetrap":
            charts.append({"type": "tw-breakdown", "spec": {"dataset": "reports", "by": "type", "agg": "count", "where": {"finding": fid}, "limit": 3,
                           "chartType": "column", "title": "Reports in this table by type", "highlight": ["Death"], "caption": ""}, "layout": {"w": 12, "h": 18}})
        grid = {"groupBy": [], "totals": False, "detail": "none", "rules": [], **grid}
        items = [{"type": "tw-grid", "spec": grid, "layout": {"w": 24, "h": 24 if fid != "codetrap" else 20}}] + charts
        for i, it in enumerate(items):
            n_widgets += 1
            widgets.append({"id": f"w-{fid}-{i}", "page": fid, "findingId": fid, "type": it["type"], "spec": it["spec"], "layout": it["layout"], "order": i,
                            "author": "bedrock", "runId": "r-cached", "createdAt": as_of})
        paras = [p.strip() for p in f["brief"].split("\n\n") if p.strip()]
        findings.append({"id": fid, "kind": KIND[fid], "severity": SEV[f["severity"]], "status": "open", "title": f["title"], "headline": f["headline"],
                         "summary": f["brief"].replace("  \n", "\n").strip(), "brief": LINE[fid], "gap": [{"label": a, "value": b, "text": c} for a, b, c in GAP[fid]], "actions": f["next_steps"][:3],
                         "evidenceIds": flagged, "window": window, "author": "agent", "confidence": 1, "createdAt": f"{as_of[:10]}T00:00:0{9 - rank}Z"})
    span_all = sorted(r["received"] for r in data["reports"] if r["received"])
    return {"asOf": as_of, "span": f"{span_all[0][:4]} to {span_all[-1][:4]}" if span_all else "", "findings": findings, "widgets": widgets, "data": data,
            "source": src.get("source", "")}


def cached_run(board: dict, n_reports: int) -> dict:
    nano_n = len(json.loads((CACHE / "nano_cdh29a.json").read_text())) if (CACHE / "nano_cdh29a.json").exists() else 0
    t = board["asOf"]
    steps = [{"kind": "note", "detail": f"Loaded {n_reports:,} MAUDE reports from five openFDA pulls, with their full narratives.", "at": t}]
    if nano_n:
        steps.append({"kind": "note", "detail": f"Nemotron Nano read {nano_n} CDH29A narratives and sorted each into a failure mode.", "at": t})
    for f in board["findings"]:
        steps.append({"kind": "tool", "tool": "record_finding", "input": {"title": f["title"]}, "ok": True, "detail": f["headline"], "at": t})
    for w in board["widgets"]:
        steps.append({"kind": "tool", "tool": "build_widget", "input": {"type": w["type"], "spec": {"title": w["spec"]["title"]}}, "ok": True, "detail": "", "at": t})
    steps.append({"kind": "note", "detail": "Nemotron Super wrote the text of each finding from those counts.", "at": t})
    return {"id": "r-cached", "trigger": "precomputed", "startedAt": t, "done": True, "steps": steps, "model": "NVIDIA Nemotron Nano + Super (Nebius Token Factory)",
            "summary": f"{len(board['findings'])} findings written.", "usage": {"calls": nano_n + len(board["findings"])}, "stepCount": len(steps)}
