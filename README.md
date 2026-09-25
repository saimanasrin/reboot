# Q-Chain AI

**Cold-chain remaining-life intelligence and dynamic shelf-life routing for Qatar. Hackathon prototype.**

> Q-Chain is a decision-support prototype that estimates remaining usable shelf life using simulated IoT data
> grounded in sensor variables documented by Qatar-based cold-chain providers and temperature requirements
> documented by Qatar MOPH.

It never changes a product's legal expiry date and never decides whether food is safe. It estimates the remaining
usable **quality** window from the actual journey, explains why that window changed, classifies urgency, and
recommends the compliant destination that wastes the least food.

`SENSE → RECONSTRUCT → PREDICT → EXPLAIN → CLASSIFY → OPTIMIZE → RESCUE`

## Quick start

```powershell
.\start.ps1          # Windows: venv + deps, seeds demo data on first run, builds UI, serves http://127.0.0.1:8000
.\start.ps1 -Dev     # API :8000 + Vite hot reload on http://localhost:5173
.\start.ps1 -Reseed  # rebuild the synthetic database
```
```bash
./start.sh [--dev] [--reseed]   # macOS / Linux
```

Manual steps:
```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # (bin/ on macOS/Linux)
.venv/Scripts/python -m app.seed            # ~2-3 min: trains the prototype model, generates 1,284 shipments
.venv/Scripts/python -m uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev  # http://localhost:5173 (proxies /api to :8000)
```

Demo logins: `admin/admin123`, `warehouse/warehouse123`, `distributor/distributor123`, `retailer/retailer123`
(the login page has one-click buttons). Copy `backend/.env.example` to `backend/.env` to change secrets or add
`ANTHROPIC_API_KEY`. The key turns on LLM narration in "Ask Q-Chain"; without it, a deterministic template explainer answers.

## Demo flow (the hero shipment, Q4821)

1. **Command centre:** "1,284 shipments monitored", live map, KPIs.
2. Banner: **Temperature excursion detected, shipment Q4821** (500 kg strawberries, 8-day declared life).
3. **Sensor timeline:** press *Replay sensor stream*. The excursion (≈2 h 17 m above 5 °C, peak 8.6 °C at Hamad
   airport cargo) is shaded and raises an alert as it streams in.
4. **Shelf-life analysis:** 6.2 d declared remaining → ≈2.4 d estimated usable window (the expiry date is unchanged).
5. **Why did the shelf life drop?** Waterfall: temperature ≈ −2.0 d, warehouse dwell ≈ −1.1 d, transit ≈ −0.5 d,
   handling ≈ −0.3 d, each with its sensor evidence.
6. Classified **MID / ACCELERATE**, risk **HIGH**, confidence ≈ 82%.
7. **SAVE THIS SHIPMENT** walks through 7 steps and compares routes: original DC route ≈ 32% expected waste vs
   optimized ≈ 10%. The plan sends ≈ 340 kg to Retailer A, ≈ 130 kg to the restaurant network, and the rest to rapid sale.
8. **What if?** Do nothing, Retailer A, Retailer B, discount 10/20%, accelerate, rescue, optimized.
9. **Ask Q-Chain** narrates the outputs, with citations and guardrails.

All figures come from the seeded synthetic dataset (fixed clock 25 Sep 2026 14:00, seed 4821), so the demo is reproducible.

## Architecture

| Layer | Module |
|---|---|
| IoT sensor simulator (scenarios A–E, OU temperature process, doors, shocks, battery) | `backend/app/simulator.py` |
| Data ingestion API (device key) | `POST /api/sensors/ingest` |
| Time-series / shipment DB (SQLite default, PostgreSQL via env) | `models.py`, `db.py` |
| Data quality: missing, outliers, impossible values, duplicates, disconnects, stale GPS | `data_quality.py` |
| Feature engineering (journey reconstruction) | `features.py` |
| Shelf-life Layer 1: Q10 + abuse/dwell/transit physics-inspired model | `physics.py` |
| Shelf-life Layer 2: GradientBoosting + 10/90% quantile models on synthetic journeys | `ml.py` |
| Risk / confidence, classification (GOOD/MID/LOW/HOLD → NORMAL/ACCELERATE/RESCUE/HOLD) | `pipeline.py` |
| Compliance rule engine: official MOPH thresholds kept separate from prototype policies | `compliance.py` |
| Demand forecast (seasonal-naive) + FIFO sell-through | `demand.py` |
| Routing optimizer + what-if simulator | `optimizer.py` |
| Explainability engine | `explain.py` |
| Decision agent: LLM narration only, JSON schema, guardrails, template fallback | `agent.py` |
| Auth (signed tokens), RBAC, audit log | `auth.py` |
| Web dashboard: React, TS, Vite, Tailwind, Recharts, Leaflet | `frontend/` |

API: `GET /api/dashboard`, `GET /api/shipments`, `GET /api/shipments/{id}`, `GET /api/shipments/{id}/sensor-history`,
`POST /api/shipments/{id}/predict`, `GET /api/shipments/{id}/explanation`, `POST /api/shipments/{id}/optimize`,
`POST /api/shipments/{id}/simulate`, `POST /api/shipments/{id}/agent-explanation`, `POST /api/sensors/ingest`,
`POST /api/simulator/shipments`, `GET /api/reference`, `GET /api/audit`. Interactive docs are at `/docs`.

## Key modelling choices

- **Buyers accept lots on the declared date, but the lots sell within the usable window.** Status-quo routes are
  evaluated that way. That is the gap Q-Chain exposes: a DC accepts 500 kg of strawberries because 6.2 days remain
  on the label, then ~32% goes unsold. The optimizer uses the stricter usable-window eligibility.
- **Blend:** 60% physics layer + 40% ML layer. Loss attribution is scaled so the waterfall sums exactly to the final loss.
- **Confidence** is a heuristic from the ML quantile interval, physics/ML agreement, data quality and hours without data.
- **Compliance can only restrict.** HOLD blocks every sale and redistribution scenario. Rescue channels are phrased as
  "eligible for food-rescue review, subject to applicable food-safety and organizational acceptance requirements."

## Scientific honesty

- Sensor readings are **synthetic**. No company has supplied data, and readings are not Vodafone Qatar data.
- `demo_product_parameters` are illustrative, not legal shelf-life rules. `official_regulatory_thresholds` cite MOPH.
- The ML model is trained on synthetic labels. Its metrics describe synthetic holdout data only, and it is not validated or production-ready.
- The system does not determine food safety and does not claim Qatar lacks cold-chain monitoring or food-rescue systems.

Sources: [Vodafone Qatar IoT Asset Tracking](https://www.vodafone.qa/en/business/services/iot/asset-tracking) ·
[MOPH Watheq guidebook](https://emsfsa.moph.gov.qa/en/MOPH_Documents/Registration%20Documents/Users%20Guidebook-Part%201-Regestration%20of%20Company%20%20Related%20Products%20by%20Watheq%20System.pdf) ·
[MOPH food-service guidelines](https://www.moph.gov.qa/_layouts/15/download.aspx?SourceUrl=%2FAdmin%2FLists%2FPublicationsAttachments%2FAttachments%2F140%2FFood-service-establishment-Guidelines-English.pdf) ·
[Infotech Qatar cold-chain](https://infotech.qa/services/iot/cold-chain-management/)
