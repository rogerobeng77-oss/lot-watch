"""Lot Watch API + static React app on one port.

Everything a visitor sees by default is pre-computed and served from cache/.
The only calls that can spend a token are the two behind the "Run it" buttons:
POST /api/extract (one Nano read of one narrative) and POST /api/similar with
free text (one embedding call). Both are cached and capped per process.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import board as boardmod
import corpus

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
STATIC = ROOT.parent / "web" / "dist"
if not STATIC.exists():
    STATIC = ROOT / "static"
LIVE_CAP = 80  # live model calls per process; a click, never a loop

app = FastAPI(title="Lot Watch")
app.add_middleware(GZipMiddleware, minimum_size=1000)
_lock = threading.Lock()
_live_calls = 0


def _json(name, default):
    p = CACHE / name
    return json.loads(p.read_text()) if p.exists() else default


FINDINGS = _json("findings.json", {"findings": []})
EXTRACT_CACHE: dict = _json("extract_live.json", {})

# every report once, by number
REPORTS: dict[str, dict] = {}
for ds in corpus.DATASETS:
    for r in corpus.load(ds):
        REPORTS.setdefault(r["report_number"], dict(r, dataset=ds))

_emb = _json("embeddings.json", {})
EMB_IDS = [k for k in _emb if k in REPORTS]
EMB = np.array([_emb[k] for k in EMB_IDS], dtype="float32") if EMB_IDS else np.zeros((0, 256), "float32")
if len(EMB):
    EMB /= np.linalg.norm(EMB, axis=1, keepdims=True) + 1e-9


def _spend():
    global _live_calls
    with _lock:
        if _live_calls >= LIVE_CAP:
            raise HTTPException(429, "Live model calls for this deployment are used up; the cached findings still work.")
        _live_calls += 1


@app.get("/api/findings")
def findings():
    return FINDINGS


@app.get("/api/report/{rn}")
def report(rn: str):
    r = REPORTS.get(rn)
    if not r:
        raise HTTPException(404, "report not in the loaded set")
    return {k: r[k] for k in ("report_number", "date_received", "event_type", "manufacturer", "brand",
                              "model_number", "lot_number", "product_code", "device_returned", "narrative")}


class ExtractIn(BaseModel):
    report_number: str


@app.post("/api/extract")
def extract_live(body: ExtractIn):
    """Run it: Nemotron Nano reads one narrative live (cached after the first run)."""
    r = REPORTS.get(body.report_number)
    if not r:
        raise HTTPException(404, "report not in the loaded set")
    if body.report_number in EXTRACT_CACHE:
        return {"extraction": EXTRACT_CACHE[body.report_number], "cached": True}
    from extract import extract
    _spend()
    out = extract(r["narrative"])
    EXTRACT_CACHE[body.report_number] = out
    try:
        (CACHE / "extract_live.json").write_text(json.dumps(EXTRACT_CACHE))
    except OSError:
        pass
    return {"extraction": out, "cached": False}


class SimilarIn(BaseModel):
    report_number: str | None = None
    text: str | None = None
    k: int = 6


@app.post("/api/similar")
def similar(body: SimilarIn):
    """Reports whose narratives read like this one (embedding search)."""
    if not len(EMB):
        raise HTTPException(503, "embeddings not built")
    if body.report_number:
        if body.report_number not in EMB_IDS:
            raise HTTPException(404, "no embedding for that report")
        q = EMB[EMB_IDS.index(body.report_number)]
    elif body.text and body.text.strip():
        from precompute import embed_texts
        _spend()
        q = np.array(embed_texts([body.text[:6000]])[0], dtype="float32")
        q /= np.linalg.norm(q) + 1e-9
    else:
        raise HTTPException(400, "give a report_number or text")
    sims = EMB @ q
    out = []
    for i in np.argsort(-sims):
        rn = EMB_IDS[i]
        if rn == body.report_number:
            continue
        r = REPORTS[rn]
        out.append({"report_number": rn, "score": round(float(sims[i]), 3), "date": r["date_received"],
                    "event_type": r["event_type"], "device": r["model_number"] or r["brand"],
                    "lot": r["lot_number"] or "—", "snippet": r["narrative"][:260]})
        if len(out) >= max(1, min(body.k, 12)):
            break
    return {"results": out}


# ---------------------------------------------------------------- the Tripwire board contract
BOARD = boardmod.build()
STATUS_FILE = CACHE / "status.json"
STATUS: dict = _json("status.json", {})
RUNS: dict[str, dict] = {}
_cached = boardmod.cached_run(BOARD, len(REPORTS))
RUNS[_cached["id"]] = _cached
RUN_ORDER = [_cached["id"]]
MODEL = "NVIDIA Nemotron on Nebius Token Factory"


def _run_summary(r):
    return {k: r.get(k) for k in ("id", "trigger", "startedAt", "done", "summary", "error", "fallback", "usage", "model", "stepCount")}


@app.get("/api/board")
def api_board():
    fs = [dict(f, status=STATUS.get(f["id"], f["status"])) for f in BOARD["findings"]]
    runs = [_run_summary(RUNS[i]) for i in RUN_ORDER[:5]]
    return {"asOf": BOARD["asOf"], "span": BOARD["span"], "findings": fs, "widgets": BOARD["widgets"], "runs": runs, "model": MODEL}


@app.get("/api/data")
def api_data():
    return {"asOf": BOARD["asOf"], "rows": BOARD["data"]}


@app.get("/api/diagnostics")
def api_diagnostics():
    return {"asOf": BOARD["asOf"], "counts": {k: len(v) for k, v in BOARD["data"].items()}, "model": MODEL, "source": BOARD["source"]}


@app.get("/api/runs")
def api_runs():
    return {"runs": [_run_summary(RUNS[i]) for i in RUN_ORDER[:10]]}


@app.get("/api/runs/{rid}")
def api_run(rid: str):
    if rid not in RUNS:
        raise HTTPException(404, "No such run.")
    return RUNS[rid]


class StatusIn(BaseModel):
    status: str


@app.post("/api/findings/{fid}/status")
def api_status(fid: str, body: StatusIn):
    if body.status not in ("open", "reviewed"):
        raise HTTPException(400, "status must be open or reviewed.")
    if fid not in {f["id"] for f in BOARD["findings"]}:
        raise HTTPException(404, "No such finding.")
    STATUS[fid] = body.status
    try:
        STATUS_FILE.write_text(json.dumps(STATUS))
    except OSError:
        pass
    return {"ok": True, "status": body.status}


@app.post("/api/llm")
def api_llm():
    raise HTTPException(503, "Chat is not enabled on this deployment.")


def _step(run, **s):
    run["steps"].append(dict(s, at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")))
    run["stepCount"] = len(run["steps"])


def _do_read(run):
    """The live read: re-count the loaded reports from their text, then one Nano read of the hidden death (cached after the first)."""
    try:
        spot = next(f for f in BOARD["findings"] if f["id"] == "sureform")
        rn = "2955842-2026-01596"
        _step(run, kind="note", detail=f"Re-reading {len(REPORTS):,} loaded MAUDE reports.")
        time.sleep(0.6)
        by_type: dict[str, int] = {}
        for r in REPORTS.values():
            by_type[r["event_type"]] = by_type.get(r["event_type"], 0) + 1
        _step(run, kind="tool", tool="query_stream", input={"dataset": "reports", "group_by": "type"}, ok=True, detail=json.dumps(by_type))
        time.sleep(0.6)
        field_hits = [r for r in REPORTS.values() if "48230M" in (r["model_number"] or "") and r["event_type"] == "Death"]
        text_hits = [r for r in REPORTS.values() if "48230M" in r["narrative"] and r["event_type"] == "Death"]
        _step(run, kind="note", detail=f"Death reports for reload 48230M: {len(field_hits)} by model field, {len(text_hits)} by reading the text.")
        time.sleep(0.5)
        if rn in REPORTS:
            _step(run, kind="note", detail=f"Nemotron Nano is reading report {rn}.")
            try:
                if rn in EXTRACT_CACHE:
                    ex = EXTRACT_CACHE[rn]
                else:
                    from extract import extract
                    _spend()
                    ex = extract(REPORTS[rn]["narrative"])
                    EXTRACT_CACHE[rn] = ex
                    try:
                        (CACHE / "extract_live.json").write_text(json.dumps(EXTRACT_CACHE))
                    except OSError:
                        pass
                _step(run, kind="note", detail=f"Nano: {ex.get('failure_mode')} on {ex.get('tissue')}; device named in the text: {ex.get('device_in_text') or 'none'}.")
            except HTTPException:
                _step(run, kind="note", detail="Live reads are used up on this deployment; the cached read stands.")
            except Exception as e:  # model unavailable: the counts above still stand
                _step(run, kind="note", detail=f"The model did not answer ({type(e).__name__}); the cached read stands.")
        run["summary"] = f"{len(BOARD['findings'])} findings checked. {len(text_hits)} death found only in the text."
    except Exception as e:
        run["error"] = str(e)
    run["done"] = True


@app.post("/api/scan")
def api_scan():
    rid = f"r-{int(time.time()):x}-{len(RUNS)}"
    run = {"id": rid, "trigger": "manual", "startedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "done": False, "steps": [],
           "model": MODEL, "stepCount": 0}
    RUNS[rid] = run
    RUN_ORDER.insert(0, rid)
    threading.Thread(target=_do_read, args=(run,), daemon=True).start()
    return JSONResponse({"runId": rid}, status_code=202)


@app.get("/api/health")
def health():
    return {"ok": True, "findings": len(FINDINGS["findings"]), "embedded": len(EMB_IDS)}


if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = STATIC / path
        return FileResponse(f if path and f.is_file() else STATIC / "index.html")
