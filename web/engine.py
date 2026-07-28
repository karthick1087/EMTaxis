"""EMTaxis core engine — published dual signatures, correct scale handling."""

from __future__ import annotations

import base64
import json
from collections import Counter
from io import BytesIO
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

ROOT = Path(__file__).resolve().parents[1]

plt.rcParams.update(
    {
        "figure.facecolor": "#ffffff",
        "axes.facecolor": "#ffffff",
        "axes.edgecolor": "#cbd5e1",
        "axes.labelcolor": "#0f172a",
        "text.color": "#0f172a",
        "xtick.color": "#475569",
        "ytick.color": "#475569",
        "grid.color": "#e2e8f0",
        "savefig.facecolor": "#ffffff",
        "font.family": "DejaVu Sans",
        "font.size": 11,
    }
)

STATE_COLORS = {
    "epithelial": "#0369a1",
    "hybrid": "#6d28d9",
    "mesenchymal": "#be185d",
    # legacy
    "epithelial-like": "#0369a1",
    "intermediate": "#6d28d9",
    "transitioning": "#6d28d9",
    "mesenchymal-like": "#be185d",
}
STATE_ORDER_PREF = ["epithelial", "hybrid", "mesenchymal"]


class EMTEngine:
    def __init__(self):
        self.model = joblib.load(ROOT / "results" / "best_model.pkl")
        self.scaler = joblib.load(ROOT / "results" / "scaler.pkl")
        self.le = joblib.load(ROOT / "results" / "label_encoder.pkl")
        self.class_names = list(self.le.classes_)
        self.state_order = [c for c in STATE_ORDER_PREF if c in self.class_names] or list(
            self.class_names
        )

        # Feature genes from training
        feat_path = ROOT / "results" / "feature_genes.txt"
        if feat_path.exists():
            self.gene_columns = [
                ln.strip() for ln in open(feat_path) if ln.strip()
            ]
        else:
            with open(ROOT / "emt_genes.txt") as f:
                self.gene_columns = [ln.strip() for ln in f if ln.strip()]

        # Feature list must match scaler (no legacy EMT_score feature)
        n_expected = int(self.scaler.n_features_in_)
        if len(self.gene_columns) != n_expected:
            raise ValueError(
                f"Feature count mismatch: genes={len(self.gene_columns)} "
                f"scaler={n_expected}. Re-run: python build_gene_panel.py && "
                "python prepare.py && python train.py"
            )
        self.use_mean_score_feature = False  # never inject old mean EMT_score

        # Reference means/stds for imputation + dual-score z projection
        ref_path = ROOT / "results" / "gene_reference_stats.csv"
        self.ref_mean = {}
        self.ref_std = {}
        if ref_path.exists():
            ref = pd.read_csv(ref_path)
            self.ref_mean = dict(zip(ref["gene"].astype(str), ref["mean"].astype(float)))
            if "std" in ref.columns:
                self.ref_std = dict(zip(ref["gene"].astype(str), ref["std"].astype(float)))

        # SHAP optional
        shap_path = ROOT / "results" / "shap_explainer.pkl"
        self.explainer = joblib.load(shap_path) if shap_path.exists() else None

        # Consensus E/M panels for dual EMT axis (E_z, M_z, EMT_axis_S)
        self.epi_genes = self._load_list(
            ROOT / "gene_sets" / "matched_epithelial.txt"
        ) or self._load_list(ROOT / "gene_sets" / "consensus_epithelial.txt")
        self.mes_genes = self._load_list(
            ROOT / "gene_sets" / "matched_mesenchymal.txt"
        ) or self._load_list(ROOT / "gene_sets" / "consensus_mesenchymal.txt")
        # keep only genes present in the trained feature set
        gset = set(self.gene_columns)
        self.epi_genes = [g for g in self.epi_genes if g in gset]
        self.mes_genes = [g for g in self.mes_genes if g in gset]
        if len(self.epi_genes) < 5 or len(self.mes_genes) < 5:
            raise ValueError(
                "E/M panel genes missing from model features. "
                "Re-run prepare.py and train.py."
            )

        meta_path = ROOT / "results" / "prepare_meta.json"
        self.meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    @staticmethod
    def _load_list(path: Path) -> list[str]:
        if not path.exists():
            return []
        return [ln.strip() for ln in open(path) if ln.strip()]

    @staticmethod
    def _fig_b64(fig, dpi=140) -> str:
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")

    def predict_file(self, path: str | Path, data_type: str) -> dict:
        """
        data_type:
          - 'log2(TPM + 1)' : already training scale
          - 'TPM (no log)'  : true TPM → log2(TPM+1)
          - 'Raw counts'    : full library CPM on ALL uploaded genes, then
                              extract features → log2(CPM+1)
                              NOTE: CPM ≠ TPM; documented approximation.
        """
        # normalize scale label
        dt = (data_type or "").strip()
        if "raw" in dt.lower():
            data_type = "Raw counts"
        elif "no log" in dt.lower() or dt.lower().startswith("tpm"):
            data_type = "TPM (no log)"
        else:
            data_type = "log₂(TPM + 1)"

        df = pd.read_csv(path, index_col=0)
        df = df[~df.index.astype(str).str.startswith("__")]
        df.index = df.index.astype(str).str.strip().str.upper()
        # genes × samples matrix expected
        # coerce numeric
        df = df.apply(pd.to_numeric, errors="coerce")

        samples = df.columns.astype(str).tolist()

        if data_type == "Raw counts":
            # Library size = sum over ALL genes in file (genome-wide if provided)
            lib = df.sum(axis=0).replace(0, np.nan)  # per sample (column)
            cpm = df.div(lib, axis=1) * 1e6
            work = np.log2(cpm.clip(lower=0) + 1)
            conversion = (
                "Raw counts → CPM (all genes in file as library) → log₂(CPM+1). "
                "Note: CPM is not TPM (no gene-length normalization)."
            )
        elif data_type == "TPM (no log)":
            work = np.log2(df.clip(lower=0) + 1)
            conversion = "TPM → log₂(TPM + 1)"
        else:
            work = df
            conversion = "Assumed already log₂(TPM + 1)"

        # Build samples × features; impute missing genes with training mean (not 0)
        X = pd.DataFrame(index=samples, columns=self.gene_columns, dtype=float)
        matched = 0
        for g in self.gene_columns:
            if g in work.index:
                X[g] = work.loc[g].to_numpy()
                matched += 1
            else:
                X[g] = self.ref_mean.get(g, np.nan)

        if matched < max(10, int(0.2 * len(self.gene_columns))):
            raise ValueError(
                f"Only {matched}/{len(self.gene_columns)} signature genes found. "
                "Check gene symbols (rows) and file format."
            )

        # Remaining NA → column training mean then 0
        for g in self.gene_columns:
            if X[g].isna().any():
                fill = self.ref_mean.get(g, float(X[g].mean(skipna=True) or 0.0))
                X[g] = X[g].fillna(fill)
        X = X.fillna(0.0)

        feat_mat = X[self.gene_columns]

        # Dual-program scores (always defined): E_z, M_z, EMT_axis_S = M_z - E_z
        axis_info = self._axis_scores(feat_mat)

        Xs = self.scaler.transform(feat_mat)
        probas = self.model.predict_proba(Xs)
        pred_idx = np.argmax(probas, axis=1)
        pred_cls = [str(self.class_names[i]) for i in pred_idx]
        conf = probas.max(axis=1)

        rows = []
        for i, sample in enumerate(samples):
            e = round(float(axis_info["E"][i]), 4)
            m = round(float(axis_info["M"][i]), 4)
            s = round(float(axis_info["S"][i]), 4)
            row = {
                "sample": str(sample),
                "state": pred_cls[i],
                "confidence": round(float(conf[i] * 100), 1),
                # dual scores (preferred names)
                "E_z": e,
                "M_z": m,
                "EMT_axis_S": s,
                # aliases for UI / download compatibility
                "E_score": e,
                "M_score": m,
                "axis_S": s,
                "EMT_score": s,  # defined as dual-program axis S (not old mean Hallmark)
            }
            for j, c in enumerate(self.class_names):
                row[f"p_{c}"] = round(float(probas[i, j] * 100), 1)
            rows.append(row)

        counts = Counter(pred_cls)
        n = len(rows)
        summary = {
            "n_samples": n,
            "genes_mapped": matched,
            "genes_total": len(self.gene_columns),
            "mapping_pct": round(matched / len(self.gene_columns) * 100, 1),
            "conversion": conversion,
            "data_type": data_type,
            "mean_confidence": round(float(conf.mean() * 100), 1),
            "counts": {str(c): int(counts.get(c, 0)) for c in self.state_order},
            "pcts": {
                str(c): round(100 * counts.get(c, 0) / n, 1) if n else 0
                for c in self.state_order
            },
            "signatures": {
                "panel": "multi-GMT consensus EMT (MSigDB 2023.2.Hs)",
                "n_E_source_sets": self.meta.get("n_E_source_sets"),
                "n_M_source_sets": self.meta.get("n_M_source_sets"),
                "n_features": self.meta.get("n_features", len(self.gene_columns)),
                "citation": (
                    "Consensus genes from Hallmark, Foroutan, Hollern, Sarrio, "
                    "Gotzmann, Kohn, Jechlinger, Reactome, WikiPathways EMT sets"
                ),
            },
        }

        cohort_img = self._cohort_plot(counts, pred_cls, conf, axis_info["S"])

        return {
            "summary": summary,
            "rows": rows,
            "cohort_img": cohort_img,
            "samples": samples,
            "X": feat_mat,
            "probas": probas,
        }

    def _axis_scores(self, X: pd.DataFrame) -> dict:
        """Project E/M using training gene means/SDs (always returns finite arrays)."""

        def zcols(genes):
            cols = [g for g in genes if g in X.columns]
            n = len(X)
            if not cols:
                return np.zeros(n, dtype=float)
            arr = X[cols].to_numpy(dtype=float)
            means = np.array(
                [float(self.ref_mean.get(g, np.nanmean(arr[:, i]))) for i, g in enumerate(cols)],
                dtype=float,
            )
            stds = np.array(
                [
                    float(self.ref_std.get(g, np.nanstd(arr[:, i]) or 1.0))
                    for i, g in enumerate(cols)
                ],
                dtype=float,
            )
            stds = np.where(~np.isfinite(stds) | (stds < 1e-8), 1.0, stds)
            means = np.where(np.isfinite(means), means, 0.0)
            z = (arr - means) / stds
            z = np.where(np.isfinite(z), z, 0.0)
            return z.mean(axis=1)

        E = zcols(self.epi_genes)
        M = zcols(self.mes_genes)
        S = M - E
        return {"E": E, "M": M, "S": S}

    def _cohort_plot(self, counts, pred_cls, conf, axis_S) -> str:
        order = self.state_order
        fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.6))
        vals = [counts.get(c, 0) for c in order]
        colors = [STATE_COLORS.get(c, "#64748b") for c in order]
        bars = axes[0].barh(order, vals, color=colors, height=0.55)
        axes[0].set_xlabel("Count")
        axes[0].set_title("Predicted dual-signature strata")
        axes[0].grid(axis="x", alpha=0.35)
        mx = max(vals) if vals else 1
        for b, v in zip(bars, vals):
            axes[0].text(
                v + mx * 0.02 + 0.05,
                b.get_y() + b.get_height() / 2,
                str(v),
                va="center",
                fontsize=10,
            )

        # Axis S by predicted class
        conf_by = {c: [] for c in order}
        for cls, s in zip(pred_cls, axis_S):
            if cls in conf_by:
                conf_by[cls].append(float(s))
        data = [conf_by[c] if conf_by[c] else [0.0] for c in order]
        bp = axes[1].boxplot(
            data,
            labels=order,
            patch_artist=True,
            widths=0.5,
            medianprops=dict(color="#0f172a", linewidth=1.5),
        )
        for patch, c in zip(bp["boxes"], colors):
            patch.set_facecolor(c)
            patch.set_alpha(0.45)
        axes[1].set_ylabel("Axis S = M − E (projected)")
        axes[1].set_title("Dual-signature axis by prediction")
        axes[1].grid(axis="y", alpha=0.35)
        fig.tight_layout()
        return self._fig_b64(fig)

    def explain_sample(self, X: pd.DataFrame, probas: np.ndarray, sample: str) -> dict:
        samples = list(X.index.astype(str))
        if sample not in samples:
            raise ValueError(f"Sample not found: {sample}")
        idx = samples.index(sample)
        sample_data = X.iloc[[idx]]
        sample_scaled = self.scaler.transform(sample_data)
        sample_proba = np.asarray(probas[idx]).ravel()
        pred_i = int(np.argmax(sample_proba))
        pred_class = self.class_names[pred_i]
        color = STATE_COLORS.get(pred_class, "#4f46e5")
        conf = float(sample_proba.max())

        proba_map = {
            c: float(sample_proba[self.class_names.index(c)]) for c in self.class_names
        }

        # SHAP if available
        feature_names = list(X.columns)
        if self.explainer is not None:
            shap_vals = self.explainer.shap_values(sample_scaled)
            if isinstance(shap_vals, list):
                shap_vec = np.asarray(shap_vals[pred_i][0]).ravel()
            else:
                arr = np.asarray(shap_vals)
                shap_vec = arr[0, :, pred_i] if arr.ndim == 3 else arr[0].ravel()
        else:
            # fallback: coefficient-like from local scaled values magnitude
            shap_vec = sample_scaled.ravel() * 0.0

        top_n = min(15, len(feature_names))
        order_idx = np.argsort(np.abs(shap_vec))[::-1][:top_n][::-1]
        names = [feature_names[i] for i in order_idx]
        vals = shap_vec[order_idx]
        bar_colors = ["#059669" if v > 0 else "#dc2626" for v in vals]

        fig1, ax1 = plt.subplots(figsize=(7.8, 5.8))
        ax1.barh(range(len(names)), vals, color=bar_colors, height=0.72)
        ax1.set_yticks(range(len(names)))
        ax1.set_yticklabels(names, fontsize=10)
        ax1.axvline(0, color="#94a3b8", lw=1)
        ax1.set_xlabel("SHAP value")
        ax1.set_title(f"Gene drivers — {sample}", color=color, fontweight="600")
        ax1.grid(axis="x", alpha=0.35)
        fig1.tight_layout()
        shap_img = self._fig_b64(fig1)

        order = self.state_order
        fig2, ax2 = plt.subplots(figsize=(6.8, 3.2))
        y_pos = np.arange(len(order))
        pvals = [proba_map.get(c, 0.0) for c in order]
        cols = [STATE_COLORS.get(c, "#64748b") for c in order]
        ax2.barh(y_pos, pvals, color=cols, height=0.55)
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(order)
        ax2.set_xlim(0, 1.08)
        ax2.set_xlabel("Probability")
        ax2.set_title("Class probabilities", fontweight="600")
        for i, v in enumerate(pvals):
            ax2.text(v + 0.02, i, f"{v:.1%}", va="center", fontsize=10)
        ax2.grid(axis="x", alpha=0.35)
        fig2.tight_layout()
        prob_img = self._fig_b64(fig2)

        return {
            "sample": sample,
            "state": pred_class,
            "color": color,
            "confidence": round(conf * 100, 1),
            "probabilities": {c: round(proba_map.get(c, 0) * 100, 1) for c in order},
            "shap_img": shap_img,
            "prob_img": prob_img,
        }


engine = EMTEngine()
