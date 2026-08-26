# SHADOWINTEL

A local-first, fully synthetic investigation-intelligence prototype for **Operation ShadowLink**. It provides a FastAPI evidence/graph service and a polished Next.js workspace covering command center, ingestion, network exploration, entity dossiers, anomaly analysis, timeline, assistant, and evidence/reports.

> ShadowIntel assists investigation and evidence analysis. It does not determine guilt, criminality, or legal responsibility.

## Quick start

The simplest demo startup is:

```bash
docker compose up --build
```

Open `http://localhost:3000`. The API documentation is at `http://127.0.0.1:8010/docs`.

For local development:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

## Data lifecycle

The backend persists the seeded case and every uploaded document in `backend/data/shadowintel.db`. Uploading TXT/CSV, PDF, or (when Tesseract is installed) an image stores the original file, computes SHA-256, extracts text, resolves mentions against current entities, creates provenance-linked graph relationships and timeline events, and makes the new source retrievable by the assistant.

Reset the demo to the deterministic Operation ShadowLink baseline:

```bash
python backend/scripts/seed_shadowlink.py
```

`python backend/scripts/reset_database.py` performs the same reset explicitly. Image and scanned-PDF OCR require the local **Tesseract** executable in addition to the Python dependencies; install Tesseract for Windows and ensure `tesseract` is on `PATH`. The API returns a clear validation error when it is unavailable rather than claiming OCR occurred. Text PDFs use `pdfplumber`; captioned YouTube URLs use `youtube-transcript-api` and never download or transcribe audio.

## Configuration and architecture

Copy `.env.example` for optional service settings. No external keys, Neo4j, PostgreSQL, or paid model API are required for the deterministic demo. The data layer is intentionally in-memory for reliable laptop demonstrations and exposes clear API boundaries for Neo4j/PostgreSQL adapters. Synthetic generation creates 60 fictional people, 30 phones, 20 accounts, 10 organizations, 15 locations, 330 CDR events, 120 transactions, 150 location observations and 26 reports. NetworkX supplies degree, betweenness, PageRank-style priority and community fallback analytics.

`backend/app/data.py` contains deterministic synthetic data, provenance, hashing, analytics and explainable anomalies. `backend/app/main.py` exposes ingestion, graph, shortest path, timeline, evidence, assistant and report APIs. `frontend/app/page.tsx` is the connected investigation workspace.

## Hybrid anomaly and risk scoring

The existing deterministic rules remain the source of every anomaly alert (unusual transaction amount, communication burst, and location overlap). Each alert is then enriched by the same `/api/anomalies` endpoint with an explainable 0–100 hybrid risk score:

- **Rule score** is the existing rule confidence scaled to 0–100.
- **ML anomaly score** uses local scikit-learn Isolation Forest over the alert's rule score, relationship count, NetworkX degree and betweenness centrality, risk-signal connections, and evidence count. It uses no external API or training data.
- **Graph score** combines relationship count, degree centrality, betweenness centrality, and direct/proximate connections to entities involved in other rule signals.

The final score is a normalized weighted combination (default: 50% rule, 25% ML, 25% graph). Adjust `HYBRID_RISK_RULE_WEIGHT`, `HYBRID_RISK_ML_WEIGHT`, and `HYBRID_RISK_GRAPH_WEIGHT` in `backend/.env`; weights are automatically normalized. Each response includes the actual input feature values and top explanation factors. For fewer than five alerts, materially identical feature rows, or a missing optional scikit-learn installation, ML reports a neutral score of 50 and says why instead of fabricating an outlier result.

## Tests

```bash
cd backend
pytest
```

The tests cover synthetic scale, analytics, graph shortest paths, evidence SHA-256 verification, and API availability.

## Demo walkthrough

Start at Command Center, upload any TXT/CSV on Intelligence Ingestion, explore P-017 in the graph (analytics determine its priority), open its dossier, inspect the explainable anomaly cards and timeline, ask the assistant why entities connect, then verify an evidence item and generate the report.

## Limitations

The default repository is SQLite, selected for reliable local demonstrations. Graph analytics use NetworkX as a real local fallback, while the FastAPI graph boundary can be backed by Neo4j in a deployment. The assistant is a deterministic retrieval implementation over the current evidence store and graph, not a generative model; no paid model API is required. Docker Compose intentionally has only the two services needed for the local demo.
