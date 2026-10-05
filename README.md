# Lot Watch

Reads the free text of FDA MAUDE reports on surgical staplers and staples and surfaces what the structured fields drop: a death filed under the instrument while the recalled reload appears only in the narrative, recalled lots already named in reports before the maker's letter, and deaths filed under the staple code rather than the stapler code.

Live: https://jjmimgbgw9.ap-south-1.awsapprunner.com

## NVIDIA Nemotron and Nebius Token Factory
- **Nemotron 3 Nano** (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `extract.py`): reads one narrative and returns strict JSON (failure mode, tissue, device and lot named in the text, harm, whether the device was returned). `precompute.py` runs it over 300 CDH29A narratives; the "Run it live" button runs it on the key death report.
- **Nemotron 3 Super** (`nvidia/nemotron-3-super-120b-a12b`, `signals.py`): writes each finding's two-paragraph brief from facts computed in code. It is told never to state rates or liability.
- **Qwen3-Embedding-8B** (also on Token Factory; `precompute.py`, `/api/similar`): embeds every narrative so a described failure finds reports that read alike across product codes.
- All calls go through `nemotron.py` to Token Factory, server side only. The deployed app serves cached results; only the "Run it" buttons spend tokens, capped per process.

Every model call runs on Nebius Token Factory, which is serverless and OpenAI-compatible, so one base URL and the standard OpenAI client reached every model with no GPU and no dedicated endpoint to provision. That is what let this be built and deployed quickly. Nano handles the 300 high-volume extractions cheaply and Super writes the few briefs, so each call sits on the right-sized, right-priced model.

## Data
Real openFDA device/event, recall, enforcement and classification records (CC0) in `backend/corpus_data/`; FDA's 2019 panel figures; FDA correction letters; published court opinions. No rates are computed: MAUDE has no denominator. No court is shown to have found a stapler maker liable.

## Run
    cd backend && python -m venv venv && . venv/bin/activate && pip install -r requirements.txt
    export NEBIUS_API_KEY=...      # only needed for the Run it buttons and rebuilding the cache
    python signals.py              # rebuild cache/findings.json (live Super calls)
    uvicorn main:app --port 8091
    cd ../web && npm i && npm run build   # outputs to backend/static

Docker: `docker build -t lot-watch . && docker run -p 8080:8080 -e NEBIUS_API_KEY=... lot-watch`

Stack: Python, FastAPI, React (Vite), NVIDIA Nemotron and Qwen3-Embedding on Nebius Token Factory.

Licensed under the Apache License 2.0.
