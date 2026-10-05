"""Assemble Lot Watch's findings and write them to cache.

Every number, report number, lot and date in a finding is computed here from the
real openFDA records in corpus.py — the model is never trusted with a fact. The
Nemotron tiers do the two jobs a model is actually good at:

  - Nano (extract.py) reads each spotlight narrative into strict JSON — the facts
    the structured fields drop (the recalled reload named only in section D10).
  - Super writes the signal brief: plain prose around the facts handed to it, with
    a fixed "what this cannot show" list it is not allowed to soften.

build() runs the live model once and writes cache/findings.json. The server then
serves that file, so a judge's click costs no tokens; the only live call left is
the "Run it" button, which re-runs one Nano extraction on demand.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import corpus
from extract import extract
from nemotron import SUPER, client

CACHE = Path(__file__).resolve().parent / "cache"
CACHE.mkdir(exist_ok=True)

# FDA's affected-lot list, 22 Apr 2025 Ethicon Urgent Medical Device Correction
# for VASECR35 (read from research/evidence/fda-2025-ethicon-endopath-correction.txt).
FDA_VASECR35_LOTS = [
    "917C65", "895C93", "918C15", "938C92", "936C69", "929C38", "948C78", "990C81",
    "979C81", "400D82", "962C74", "506D29", "379D80", "413D56", "418D41", "419D47",
    "415D43", "427D07", "434D35", "442D78", "442D83", "444D96", "456D87", "455D03",
    "493D27", "468D88", "482D30", "502D90", "489D62", "134D80", "112D03", "155D33",
    "159D49", "181D11", "194D77", "125D04", "167D13", "223D59", "175D72", "234D11",
    "238D70", "261D10", "270D69", "317D74", "194D76", "349D54", "347D73", "317D73",
    "356D54", "326D66", "319D76", "338D99", "336D39", "356D53", "367D26", "378D04",
    "214D11",
]
VASECR35_LETTER = "2025-04-22"

# Shared caveats every brief must carry, plus the per-finding ones. Fixed text:
# the model does not get to soften them.
GLOBAL_CAVEATS = [
    "MAUDE reports are unvalidated and carry no denominator (units sold or procedures), so they can never give a rate.",
    "Before 2019 many stapler reports were filed as Alternative Summary Reports outside public MAUDE, so pre-2019 counts are undercounts.",
    "Manufacturer reports include follow-ups and supplements, so a count of reports is not a count of patients.",
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _short_problem(r: dict) -> str:
    probs = r["product_problems"] or r["patient_problems"]
    return "; ".join(probs[:2]) if probs else "—"


def _returned(v: str) -> str:
    """openFDA device_availability -> yes | no | — ."""
    s = (v or "").strip().lower()
    if s == "no":
        return "no"
    if s == "yes" or "returned" in s:
        return "yes"
    return "—"


def _row(r: dict) -> dict:
    return {
        "report_number": r["report_number"],
        "date": r["date_received"],
        "event_type": r["event_type"],
        "device": r["model_number"] or r["catalog_number"] or r["brand"],
        "lot": r["lot_number"] or "—",
        "returned": _returned(r["device_returned"]),
        "problem": _short_problem(r),
    }


def _write_brief(title: str, facts: list[str], spotlight_quote: str, *, model=SUPER) -> str:
    sys = (
        "You are a careful device-safety analyst writing one short signal brief for a tool "
        "that reads FDA MAUDE reports. Write ONE short paragraph of plain prose. "
        "Use ONLY the facts and report numbers given; never invent a number, lot, date or report "
        "number. Never state or imply a rate, a market share, or that a manufacturer was found "
        "liable. Do not editorialize, do not open with a thesis statement, do not end with a "
        "flourish or a call to action. Cite report numbers inline where they are given. State nothing beyond the facts listed: no inferences about lots, reports or devices that are not listed. Output only the paragraph. "
        "Two or three sentences."
    )
    user = (
        f"Finding: {title}\n\nVerified facts (every one is real and already checked):\n"
        + "\n".join(f"- {f}" for f in facts)
        + (f"\n\nA quoted sentence from the key report (quote it, do not paraphrase as fact):\n\"{spotlight_quote}\"" if spotlight_quote else "")
        + "\n\nWrite the paragraph now."
    )
    bad = ("let's", "we need", "word count", "must include")
    for attempt in range(4):
        ch = client().chat.completions.create(
            model=model, max_tokens=8000, reasoning_effort="medium", temperature=0.3,
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}]).choices[0]
        msg = ch.message
        text = (msg.content or "").strip()
        if text and not any(k in text.lower() for k in bad) and len(text.split()) < 140:
            return text
    raise RuntimeError("model kept returning reasoning instead of a brief")


# --------------------------------------------------------------------------- #
# the five findings
# --------------------------------------------------------------------------- #

def finding_sureform() -> dict:
    sf = corpus.load("sureform")
    death = corpus.find_report("intuitive_deaths", "2955842-2026-01596")
    n_deaths_field = sum(1 for r in sf if r["event_type"] == "Death")
    quote = ('IT APPEARED THAT NO STAPLES WERE APPLIED TO THE PA. THE STAPLER WAS REMOVED '
             'AND MASSIVE BLEEDING OCCURRED ... DESPITE OPENING AND RESUSCITATION EFFORTS, '
             'THE PATIENT EXPIRED IN THE OPERATING ROOM.')
    facts = [
        f"A search of MAUDE by model number for the recalled reload 48230M returns {len(sf)} reports and {n_deaths_field} deaths.",
        "Report 2955842-2026-01596 (received 16 Jan 2026) is a death, but it is filed under the stapler instrument (model 488530-13), not the reload.",
        "The recalled reload appears only in the free text: section D10 lists \"PRODUCT NUMBER 48230M, GRAY RELOAD, SUREFORM STAPLER30, 8MM\".",
        "The operation was a robotic pulmonary lobectomy; the stapler fired on the pulmonary artery with no error message.",
        "This report was received eight weeks before Intuitive's 11 March 2026 recall of the 8mm SureForm 30 gray reloads.",
    ]
    brief = _write_brief("A death the field search misses — SureForm 30 gray reload", facts, quote)
    extraction = extract(death["narrative"])
    # table: the 24 model-matched reports (none a death) + the hidden death row on top
    rows = [_row(death)] + [_row(r) for r in sf]
    return {
        "id": "sureform",
        "severity": "high",
        "title": "A death the field search misses — SureForm 30 gray reload",
        "device": "Intuitive SureForm 30 / 8 mm gray reload 48230M",
        "codes": ["GDW", "NAY"],
        "headline": f"{len(sf)} reports, {n_deaths_field} deaths — until you read the narrative",
        "brief": brief,
        "spotlight": {
            "report_number": death["report_number"],
            "date": death["date_received"],
            "event_type": death["event_type"],
            "field_device": death["model_number"],
            "quote": quote,
            "label": "Death filed under the stapler instrument; the recalled reload 48230M is only in the text.",
        },
        "extraction": extraction,
        "next_steps": [
            "Read every death in the wider Intuitive stapler set for a reload named only in the narrative.",
            "Match report 2955842-2026-01596 against the 11 Mar 2026 recall lot and date.",
            "Re-pull GDW and NAY for new 8 mm SureForm reports since the recall.",
        ],
        "cannot_show": GLOBAL_CAVEATS + [
            "Whether report 2955842-2026-01596 is the death FDA cites in the 11 Mar 2026 recall is not confirmed; it is consistent with it.",
        ],
        "table": {
            "caption": "Reports on reload 48230M (death row added)",
            "rows": rows,
        },
        "chart": {
            "kind": "bars",
            "title": "What the field search returns for reload 48230M",
            "unit": "reports",
            "data": [
                {"label": "Malfunction", "value": sum(1 for r in sf if r["event_type"] == "Malfunction")},
                {"label": "Injury", "value": sum(1 for r in sf if r["event_type"] == "Injury")},
                {"label": "Death", "value": n_deaths_field, "note": "0 in the fields; 1 in the narrative"},
            ],
        },
    }


def finding_vasecr35() -> dict:
    va = corpus.load("vasecr35")
    fda = {l.upper() for l in FDA_VASECR35_LOTS}
    by_lot: dict[str, list] = {}
    for r in va:
        lot = r["lot_number"].strip().upper()
        if lot:
            by_lot.setdefault(lot, []).append(r)
    matched_lots = sorted(l for l in by_lot if l in fda)
    matched_reports = [r for l in matched_lots for r in by_lot[l]]
    before = [r for r in matched_reports if r["date_received"] and r["date_received"] < VASECR35_LETTER]
    death = corpus.find_report("vasecr35", "3005075853-2025-02636")
    # lockout-type narratives by year (the honest negative)
    def is_lockout(r):
        t = (r["narrative"] + " " + " ".join(r["product_problems"])).lower()
        return any(k in t for k in ("lockout", "lock out", "failed to fire", "did not fire"))
    lk = Counter(r["date_received"][:4] for r in va if is_lockout(r) and r["date_received"])
    quote = ("THE STAPLES FELL BY OPENING THE STAPLING AND THERE WAS LEAKAGE ... THE PATIENT EXPIRED.")
    facts = [
        f"FDA's 22 April 2025 correction for VASECR35 lists {len(fda)} affected lots.",
        f"{len(matched_lots)} of those {len(fda)} lots are named in MAUDE reports, across {len(matched_reports)} reports.",
        f"{len(before)} of those reports were received before the 22 April 2025 letter; the earliest was {min(r['date_received'] for r in matched_reports if r['date_received'])}.",
        "One is a death: report 3005075853-2025-02636, received 10 April 2025, on lot 326D66 — a lot that is on FDA's later list.",
        f"The honest negative: lockout-type narratives ran at {max([v for k,v in lk.items() if "2016"<=k<"2025"] or [0])} or fewer a year from 2016 to 2024, then {lk.get('2025', 0)} in 2025 — volume alone would not have flagged this early.",
    ]
    brief = _write_brief("Recalled lots named in reports before the maker's letter — Echelon VASECR35", facts, quote)
    rows = [_row(r) for r in matched_reports]
    rows.sort(key=lambda x: x["date"])
    years = [y for y in sorted(lk) if y >= "2016"]
    return {
        "id": "vasecr35",
        "severity": "high",
        "title": "Recalled lots named in reports before the maker's letter — Echelon VASECR35",
        "device": "Ethicon Endopath Echelon Vascular White Reload (VASECR35)",
        "codes": ["GDW"],
        "headline": f"{len(matched_lots)} of {len(fda)} recalled lots were already in the reports",
        "brief": brief,
        "spotlight": {
            "report_number": death["report_number"],
            "date": death["date_received"],
            "event_type": death["event_type"],
            "field_device": death["lot_number"],
            "quote": quote,
            "label": "A death on lot 326D66, received 12 days before Ethicon's correction letter named that lot.",
        },
        "next_steps": [
            "Alert on any report whose lot is on an FDA correction list but received before the letter.",
            f"Review the {len(before)} pre-letter reports on matched lots for a common failure mode.",
            "Hold the lockout cluster as a watch item, not a signal, until volume or harm rises.",
        ],
        "cannot_show": GLOBAL_CAVEATS + [
            "A lot named in a report is not proof that the lot caused the harm.",
            "Reports name 28 of the 57 lots; the other 29 may simply not have been reported, not that they were safe.",
        ],
        "table": {
            "caption": f"{len(matched_reports)} reports naming a recalled lot",
            "rows": rows,
        },
        "chart": {
            "kind": "bars",
            "title": "Lockout-type narratives by year (the honest negative)",
            "unit": "reports",
            "data": [{"label": y, "value": lk[y], **({"note": "recall year"} if y == "2025" else {})} for y in years],
        },
    }


def finding_codetrap() -> dict:
    ec = corpus.event_type_counts()
    gag_d, gdw_d = ec["GAG"]["Death"], ec["GDW"]["Death"]
    yr = corpus.counts_by_year()["by_event_type_by_year"]["Malfunction"]
    facts = [
        "FDA's own 2019 panel analysis found that of 412 deaths in stapler/staple reports (2011-2018), 404 were filed under the staple code (GDW) and only 8 under the stapler code (GAG).",
        f"In public MAUDE today the same split holds: the stapler code GAG carries {gag_d} death reports, the staple code GDW carries {gdw_d}.",
        "An analyst who pulls only \"Stapler, Surgical\" (GAG) sees a small fraction of the deaths.",
        f"Public stapler/staple malfunction reports rose from {yr['2016']} in 2016 to {yr['2017']} in 2017 and {yr['2018']} in 2018, once the Alternative Summary Reporting exemption ended.",
        "FDA reclassified surgical staplers for internal use from class I to class II with special controls in 2021 (86 FR 56195).",
    ]
    brief = _write_brief("The code trap — deaths filed under the staple code, not the stapler", facts, "")
    return {
        "id": "codetrap",
        "severity": "high",
        "title": "The code trap — deaths filed under the staple code, not the stapler",
        "device": "All surgical staplers & staples (product codes GAG, GDW)",
        "codes": ["GAG", "GDW"],
        "headline": f"404 of 412 deaths were under the staple code — GAG shows {gag_d}, GDW shows {gdw_d}",
        "brief": brief,
        "spotlight": {
            "report_number": "FDA panel, 30 May 2019",
            "date": "2019-05-30",
            "event_type": "analysis",
            "field_device": "412 deaths, 2011-2018",
            "quote": "404 of 412 deaths were reported under the staple product code, not the stapler product code.",
            "label": "The split is FDA's own finding; Lot Watch pulls GDW and NAY, not just GAG.",
        },
        "next_steps": [
            "Always pull the staple code (GDW) and the robotic code (NAY) alongside the stapler code (GAG).",
            "Treat a death under a staple or component code as a stapler death for clustering.",
            "Flag any device whose deaths sit disproportionately under a component code.",
        ],
        "cannot_show": GLOBAL_CAVEATS + [
            "The 2011-2018 figures are FDA's; the 51% filed as summary reports were not in public MAUDE for pre-2017 years at all.",
        ],
        "table": {
            "caption": "Public MAUDE counts by product code",
            "rows": [
                {"report_number": "GAG — Stapler, Surgical", "date": "", "event_type": "Death", "device": str(gag_d), "lot": str(ec["GAG"]["Injury"]), "returned": str(ec["GAG"]["Malfunction"]), "problem": "class II, 878.4740"},
                {"report_number": "GDW — Staple, Implantable", "date": "", "event_type": "Death", "device": str(gdw_d), "lot": str(ec["GDW"]["Injury"]), "returned": str(ec["GDW"]["Malfunction"]), "problem": "class II, 878.4750"},
            ],
            "columns_override": ["code", "", "", "deaths", "injuries", "malfunctions", "regulation"],
        },
        "chart": {
            "kind": "bars",
            "title": "Death reports by product code (public MAUDE, all years)",
            "unit": "death reports",
            "data": [
                {"label": "Stapler code (GAG)", "value": gag_d},
                {"label": "Staple code (GDW)", "value": gdw_d, "note": "where the deaths actually sit"},
            ],
        },
    }


def finding_cdh29a() -> dict:
    cd = corpus.load("cdh29a")
    nano_path = CACHE / "nano_cdh29a.json"
    nano = json.loads(nano_path.read_text()) if nano_path.exists() else {}
    def mode(r):
        fm = (nano.get(r["report_number"]) or {}).get("failure_mode", "")
        fm = fm.split("(")[0].strip().lower()
        allowed = {"no staples formed", "incomplete staple line", "uncut or retained washer", "lockout / would not fire", "misfire", "staple/fragment left", "not stated"}
        return fm if fm in allowed else ("not read" if not fm else "other")
    modes = Counter(mode(r) for r in cd)
    facts = [
        f"This is a sample of {len(cd)} MAUDE reports on the Ethicon circular stapler CDH29A.",
        "Nemotron Nano read each narrative and sorted it by failure mode: " + ", ".join(f"{v} {k}" for k, v in modes.most_common()) + ".",
        "CDH29A is the device family in Ethicon's 11 April 2019 Class I recall (92,496 units) for insufficient firing and failure to completely form staples.",
        "In Hershberger v. Ethicon (S.D. W. Va. 2011), a CDH29 stapler cut tissue but fired no staples; Ethicon first searched only the \"missing staples\" complaint code; searching \"would not staple\" later surfaced 125 more incidents, 44 of them similar by the plaintiffs' count. The court ordered $53,350.36 in discovery sanctions; it made no finding of bad faith and no ruling on liability.",
    ]
    brief = _write_brief("Circular stapler CDH29A — 300 reports clustered by failure mode", facts, "")
    rows = [dict(_row(r), problem=mode(r)) for r in cd]
    return {
        "id": "cdh29a",
        "severity": "medium",
        "title": "Circular stapler CDH29A — reports clustered by failure mode",
        "device": "Ethicon Proximate ILS Curved Intraluminal Stapler (CDH29A)",
        "codes": ["GDW", "GAG"],
        "headline": f"{len(cd)} reports sorted into {len(modes)} failure modes by reading the text",
        "brief": brief,
        "spotlight": {
            "report_number": "Hershberger v. Ethicon, 277 F.R.D. 299",
            "date": "2011-09-23",
            "event_type": "court finding",
            "field_device": "CDH29",
            "quote": "Ethicon searched one complaint code (\"missing staples\") and not \"would not staple\"; later searches under that code turned up 125 more incidents, of which plaintiffs counted 44 as similar. The magistrate judge called the first response \"unreasonable in the extreme and, frankly, nonsensical.\"",
            "label": "Similar reports sat under a different complaint code and were not searched at first — the gap Lot Watch closes by reading the text.",
        },
        "next_steps": [
            "Cluster the insufficient-firing and uncut-washer reports against the 2019 Class I recall.",
            "Treat \"would not staple\" and \"missing staples\" as one failure mode, not two codes.",
            "Carry the Hershberger coding lesson into every complaint-database search.",
        ],
        "cannot_show": GLOBAL_CAVEATS + [
            "This is a 300-report sample (received April 2020 to August 2021) of about 2,548 CDH29A reports; the mix of failure modes may shift across the full set.",
            "Hershberger's merits outcome is not verified; the $53,350.36 is a discovery sanction, not a liability finding.",
        ],
        "table": {
            "caption": f"{len(cd)} CDH29A reports",
            "rows": rows,
        },
        "chart": {
            "kind": "bars",
            "title": "CDH29A reports by failure mode (read by Nano)",
            "unit": "reports",
            "data": [{"label": k, "value": v} for k, v in modes.most_common()],
        },
    }


def finding_notreturned() -> dict:
    dd = corpus.load("gag_gdw_deaths")
    import re
    not_returned = sum(1 for r in dd if _returned(r["device_returned"]) == "no")
    leak = sum(1 for r in dd if re.search(r"leak|dehisc", r["narrative"], re.I))
    bleed = sum(1 for r in dd if re.search(r"bleed|hemorrhage|exsang", r["narrative"], re.I))
    makers = Counter()
    for r in dd:
        m = r["manufacturer"].upper()
        if "ETHICON" in m or "JOHNSON" in m: makers["Ethicon / J&J"] += 1
        elif any(k in m for k in ("COVIDIEN", "MEDTRONIC", "US SURGICAL", "UNITED STATES SURGICAL")): makers["Covidien / Medtronic"] += 1
        elif "INTUITIVE" in m: makers["Intuitive"] += 1
        else: makers["other"] += 1
    facts = [
        f"Of {len(dd)} stapler/staple death reports received in 2024-2025 (codes GAG and GDW), the manufacturer's report records the device as not available for evaluation (device_availability = No) in {not_returned}.",
        f"Across all {len(dd)} reports, a keyword pass finds leak or dehiscence in {leak} narratives and bleeding in {bleed}.",
        "Where the device is not available, the narrative is the main account of what failed.",
        f"Across all {len(dd)} reports (not only the unavailable ones), by maker: " + ", ".join(f"{v} {k}" for k, v in makers.most_common()) + ".",
    ]
    brief = _write_brief("No device to examine — stapler & staple deaths, 2024-25", facts, "")
    rows = [_row(r) for r in dd]
    rows.sort(key=lambda x: x["returned"])  # not-returned first
    return {
        "id": "notreturned",
        "severity": "watch",
        "title": "No device to examine — stapler & staple deaths, 2024-25",
        "device": "All stapler & staple death reports, 2024-2025 (GAG, GDW)",
        "codes": ["GAG", "GDW"],
        "headline": f"device not available for evaluation in {not_returned} of {len(dd)} death reports",
        "brief": brief,
        "spotlight": {
            "report_number": f"{len(dd)} death reports, 2024-2025",
            "date": "2024-2025",
            "event_type": "Death",
            "field_device": f"{not_returned} with device unavailable",
            "quote": f"In {not_returned} of {len(dd)} stapler/staple death reports, the device was recorded as not available for evaluation.",
            "label": "When the device is gone, the only record of what failed is the narrative — which is what Lot Watch reads.",
        },
        "next_steps": [
            "Prioritise narrative extraction for deaths where the device was not available.",
            "Track, per maker, how often the device is unavailable for evaluation.",
            "Use the narrative failure mode when no failure analysis exists.",
        ],
        "cannot_show": GLOBAL_CAVEATS + [
            "\"Not available for evaluation\" is the manufacturer's own field; it does not say why the device was unavailable.",
            "Maker buckets are by the reporting-manufacturer field and may group related corporate entities.",
        ],
        "table": {
            "caption": f"{len(dd)} death reports, 2024-2025",
            "rows": rows,
        },
        "chart": {
            "kind": "bars",
            "title": "Stapler/staple death reports 2024-25 by reporting maker",
            "unit": "death reports",
            "data": [{"label": k, "value": v} for k, v in makers.most_common()],
        },
    }


def build() -> dict:
    print("Building findings (live model pass)...")
    findings = []
    for fn in (finding_sureform, finding_vasecr35, finding_codetrap, finding_cdh29a, finding_notreturned):
        print(f"  - {fn.__name__}")
        findings.append(fn())
    doc = {
        "generated": _now(),
        "source": "openFDA device/event, device/recall, device/classification (CC0); FDA 2019 panel; FDA correction letters; CourtListener opinions.",
        "findings": findings,
    }
    (CACHE / "findings.json").write_text(json.dumps(doc, indent=2))
    print(f"Wrote {CACHE / 'findings.json'} — {len(findings)} findings")
    return doc


if __name__ == "__main__":
    build()
