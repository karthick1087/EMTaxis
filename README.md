# EMTaxis

**Bulk RNA-seq classifier for epithelial / hybrid / mesenchymal (EMT) states**

Local web app + trained model. Upload a gene-expression CSV and get:

- class call (epithelial / hybrid / mesenchymal)
- class probabilities
- dual-program scores **E_z**, **M_z**, and continuous axis **S = M − E**
- SHAP gene drivers

---

## Quick start

```bash
git clone https://github.com/<YOUR_USER>/EMTaxis.git
cd EMTaxis

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python app.py
```

Open **http://127.0.0.1:7860**

Try the included demo file: `demo_expression.csv`  
(genes as rows, samples as columns, log2-scale expression).

---

## Repository layout

```
.
├── app.py                 # entry point
├── requirements.txt
├── LICENSE                # MIT
├── README.md
├── emt_genes.txt          # 388 feature genes
├── demo_expression.csv
├── gene_sets/             # consensus E / M panels (MSigDB-derived)
├── results/               # trained model, scaler, SHAP
└── web/                   # Flask UI + engine
```

---

## Input format

| Item | Requirement |
|------|-------------|
| File | CSV |
| Orientation | **genes × samples** |
| Gene IDs | HGNC symbols (`CDH1`, `VIM`, …) |
| Scale options | `log2(TPM+1)` (best), TPM, or raw counts |

Raw counts are converted as full-library CPM → log2(CPM+1).  
Missing panel genes are filled with training reference means.

---

## Deploy

### Local / LAN

```bash
python app.py
# binds 0.0.0.0:7860 → http://SERVER_IP:7860
```

Optional secret for sessions:

```bash
export EMTAXIS_SECRET_KEY="replace-with-a-long-random-string"
python app.py
```

### Production (gunicorn)

```bash
pip install gunicorn
gunicorn -w 1 -b 0.0.0.0:7860 --timeout 120 "app:app"
```

Use **one worker** if memory is limited (model + SHAP).

### systemd (example)

```ini
[Unit]
Description=EMTaxis
After=network.target

[Service]
WorkingDirectory=/opt/EMTaxis
Environment=EMTAXIS_SECRET_KEY=change-me
ExecStart=/opt/EMTaxis/.venv/bin/python app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

## Method (short)

1. **Gene panel** — multi-MSigDB consensus epithelial and mesenchymal genes (≥2 source-set support).  
2. **Labels (training)** — dual-program 2D rule on DepMap log2(TPM+1):  
   - epithelial: high E, low M  
   - mesenchymal: high M, low E  
   - hybrid: otherwise  
3. **Model** — XGBoost on 388 genes (no composite-score feature leakage).  
4. **Explain** — TreeSHAP.

For publication-style external checks with experimental E/M labels, use the research workspace scripts (`validate_em_rnaseq.py`); this repo is the **runnable tool only**.

---

## License (research only)

EMTaxis is released for **academic / non-commercial research use only**.  
See [LICENSE](LICENSE).

It is **not** a clinical or diagnostic product.

- **DepMap / CCLE** (training data): Broad DepMap data-use policy.  
- **MSigDB** gene sets: Broad / UCSD MSigDB license.  

If you use EMTaxis in a paper, cite DepMap, MSigDB, and this repository.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Missing Python package | `pip install -r requirements.txt` |
| Port 7860 busy | edit port in `app.py` |
| Few genes mapped | check HGNC symbols; genes as rows |
| OOM / slow SHAP | use gunicorn `-w 1`; close other apps |

```bash
# sanity check model files load
python -c "import joblib; joblib.load('results/best_model.pkl'); print('OK')"
```

---

## License

Research use only — see [LICENSE](LICENSE).
