"""One-time pass: Nano reads every CDH29A narrative, bge-en-icl embeds every narrative.

Results are written to cache/ so the deployed app serves them for free. Safe to
re-run: reports already in the cache are skipped.
"""
from __future__ import annotations
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import corpus
from extract import extract
from nemotron import client

CACHE = Path(__file__).resolve().parent / "cache"
CACHE.mkdir(exist_ok=True)
EMBED_MODEL = "Qwen/Qwen3-Embedding-8B"


def _load(name):
    p = CACHE / name
    return json.loads(p.read_text()) if p.exists() else {}


def nano_pass(dataset="cdh29a", workers=8):
    path = CACHE / f"nano_{dataset}.json"
    done = _load(path.name)
    todo = [r for r in corpus.load(dataset) if r["report_number"] not in done and r["narrative"].strip()]
    print(f"nano {dataset}: {len(done)} cached, {len(todo)} to read", flush=True)

    def one(r):
        try:
            return r["report_number"], extract(r["narrative"])
        except Exception as e:  # keep going; a failed report is retried next run
            print("  fail", r["report_number"], type(e).__name__, str(e)[:80], flush=True)
            return r["report_number"], None

    with ThreadPoolExecutor(workers) as ex:
        for i, (rn, out) in enumerate(ex.map(one, todo), 1):
            if out:
                done[rn] = out
            if i % 25 == 0:
                path.write_text(json.dumps(done))
                print(f"  {i}/{len(todo)}", flush=True)
    path.write_text(json.dumps(done))
    return done


def embed_texts(texts):
    resp = client().embeddings.create(model=EMBED_MODEL, input=texts, dimensions=256)
    return [d.embedding for d in resp.data]


def embed_pass(batch=16):
    path = CACHE / "embeddings.json"
    done = _load(path.name)
    todo = []
    for ds in corpus.DATASETS:
        for r in corpus.load(ds):
            if r["report_number"] not in done and r["narrative"].strip():
                todo.append(r)
    seen, uniq = set(), []
    for r in todo:
        if r["report_number"] not in seen:
            seen.add(r["report_number"]); uniq.append(r)
    print(f"embed: {len(done)} cached, {len(uniq)} to embed", flush=True)
    for i in range(0, len(uniq), batch):
        chunk = uniq[i:i + batch]
        vecs = embed_texts([c["narrative"][:6000] for c in chunk])
        for c, v in zip(chunk, vecs):
            done[c["report_number"]] = [round(x, 5) for x in v]
        if (i // batch) % 10 == 0:
            path.write_text(json.dumps(done)); print(f"  {i+len(chunk)}/{len(uniq)}", flush=True)
    path.write_text(json.dumps(done))
    return done


if __name__ == "__main__":
    which = sys.argv[1:] or ["nano", "embed"]
    if "nano" in which: nano_pass()
    if "embed" in which: embed_pass()
