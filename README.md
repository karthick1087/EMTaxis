# EMTaxis

**Web-based bulk RNA-seq classifier for epithelial / hybrid / mesenchymal (EMT) states**

EMTaxis is a **browser web interface** plus a trained model. Upload a gene-expression CSV and get EMT class calls, dual-program scores, and SHAP gene drivers — locally or online (e.g. [Render.com](https://render.com)).

| | |
|--|--|
| **Classes** | epithelial · hybrid · mesenchymal |
| **Scores** | **E_z**, **M_z**, continuous axis **S = M − E** |
| **Model** | XGBoost on a 388-gene multi-GMT consensus panel |
| **UI** | Flask web app (`web/`) — drag-and-drop CSV, results table, plots, per-sample SHAP |
| **License** | Research / non-commercial only — see [LICENSE](LICENSE) |

---

## Web interface

After you start the app (or open the hosted URL), the UI has three areas:

### Analyze
1. **Drop or browse** a CSV (genes as rows, samples as columns).  
2. Choose the **expression scale**:
   - `log₂(TPM + 1)` — recommended (training scale)
   - `TPM (not log-transformed)`
   - `Raw counts` → full-library CPM → `log₂(CPM+1)`
3. Click **Run prediction**.

### Results
- Per-sample **class** and **class probabilities**
- Dual-program scores **E_z**, **M_z**, and axis **S**
- Cohort overview plot (class mix / axis)
- Panel gene coverage and domain-adaptation notes

### Explore
- Pick a sample for **SHAP** top gene drivers (push toward epithelial / hybrid / mesenchymal)

Included demo file: [`demo_expression.csv`](demo_expression.csv)  
(use scale **log₂(TPM + 1)**).

**API (optional)**

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Web UI |
| `GET /health` | Health check (`{"ok": true, "service": "EMTaxis"}`) |
| `POST /api/predict` | Upload CSV + scale → class table + plots |
| `POST /api/explain` | SHAP for one sample after predict |

---

## Run the web app locally

```bash
git clone https://github.com/<YOUR_USER>/EMTaxis.git
cd EMTaxis

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python app.py
```

Open **http://127.0.0.1:7860** (binds `0.0.0.0`; use `$PORT` if set).

Production-style local run:

```bash
export EMTAXIS_SECRET_KEY="replace-with-a-long-random-string"
gunicorn -w 1 -b 0.0.0.0:7860 --timeout 180 "app:app"
```

Use **one worker** (`-w 1`) so the model + SHAP fit in limited RAM.

---

## Deploy the web interface online (Render.com)

This repo is ready as a free **Render Web Service** (Python + gunicorn).  
After deploy you get a public URL such as `https://emtaxis-xxxx.onrender.com` with the **same web UI**.

### 1. Push to GitHub

```bash
git remote add origin https://github.com/<YOUR_USER>/EMTaxis.git
git push -u origin main
```

### 2. Create the service on Render

**Option A — Blueprint** (`render.yaml`)

1. [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint**
2. Connect this GitHub repo and apply the blueprint (`emtaxis`)

**Option B — Manual Web Service**

| Setting | Value |
|---------|--------|
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn -w 1 -b 0.0.0.0:$PORT --timeout 180 app:app` |
| Instance type | Free |
| Health check path | `/health` |

Environment variables:

| Key | Value |
|-----|--------|
| `EMTAXIS_SECRET_KEY` | long random string (or let Render generate) |
| `PYTHON_VERSION` | `3.11.9` (optional; also in `runtime.txt`) |

### Free-tier notes

- The service **sleeps** after ~15 min idle; the first request after wake can take **30–60 s**.
- Upload `demo_expression.csv` on the live site to verify the web UI.

---

## Input format

| Item | Requirement |
|------|-------------|
| File | CSV |
| Orientation | **genes × samples** |
| Gene IDs | HGNC symbols (`CDH1`, `VIM`, …) |
| Scale | Prefer `log2(TPM+1)`; TPM or raw counts also supported in the UI |

Raw counts use **all genes in the file** as library size (CPM ≠ TPM; no gene-length correction).  
Missing panel genes are filled with DepMap training reference means.

---

## Repository layout

```
.
├── app.py                 # entry point (local + gunicorn app:app)
├── Procfile               # Render / PaaS process
├── render.yaml            # Render Blueprint
├── runtime.txt            # Python 3.11.9
├── requirements.txt
├── LICENSE                # research use only
├── README.md
├── emt_genes.txt          # 388 feature genes
├── demo_expression.csv    # small demo matrix for the web UI
├── gene_sets/             # consensus E / M panels (MSigDB-derived)
├── results/               # trained model, scaler, SHAP explainer
└── web/                   # Flask web interface
    ├── server.py          # routes: UI, /health, /api/predict, /api/explain
    ├── engine.py          # model load, scale handling, SHAP
    ├── templates/         # HTML UI
    └── static/            # CSS + JS
```

---

## Method (short)

1. **Gene panel** — multi-MSigDB consensus epithelial and mesenchymal genes (≥2 source-set support; MSigDB 2023.2.Hs).  
2. **Labels (training)** — dual-program 2D rule on DepMap `log2(TPM+1)`:
   - epithelial: high E, low M  
   - mesenchymal: high M, low E  
   - hybrid: otherwise  
3. **Model** — XGBoost on 388 genes (no composite-score feature leakage).  
4. **UI explain** — TreeSHAP per sample.

This repository is the **runnable web tool** (interface + frozen model).  
Publication-style external validation with experimental E/M labels lives in the separate research workspace (`validate_em_rnaseq.py`), not in this deploy package.

---

## License (research only)

EMTaxis is released for **academic / non-commercial research use only**.  
See [LICENSE](LICENSE).

It is **not** a clinical or diagnostic product.

Upstream data policies also apply:

- **DepMap / CCLE** (training expression)
- **MSigDB** gene sets (Broad / UCSD)

If you use EMTaxis in a paper, cite DepMap, MSigDB, and this repository.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Missing package | `pip install -r requirements.txt` |
| Port busy | `PORT=7861 python app.py` |
| Few genes mapped | HGNC symbols; genes as **rows** |
| Web UI loads but predict fails | check CSV orientation and scale radio button |
| OOM / slow SHAP | `gunicorn -w 1`; free RAM |
| Render cold start | wait 30–60 s on first hit after sleep |

```bash
# sanity-check model files
python -c "import joblib; joblib.load('results/best_model.pkl'); print('OK')"

# sanity-check web app
python -c "from app import app; print(app.test_client().get('/health').get_json())"
```
