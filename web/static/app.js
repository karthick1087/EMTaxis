/* DeepEMT front-end */
(() => {
  const $ = (sel) => document.querySelector(sel);
  const fileInput = $("#fileInput");
  const dropzone = $("#dropzone");
  const fileName = $("#fileName");
  const btnPredict = $("#btnPredict");
  const btnExplain = $("#btnExplain");
  const btnDownload = $("#btnDownload");
  const statusEl = $("#status");
  const sampleSelect = $("#sampleSelect");
  const resultsBody = $("#resultsBody");

  let selectedFile = null;
  let lastResult = null;
  let resultId = null;
  let pendingDemo = null;

  function setStatus(msg, type = "info") {
    statusEl.textContent = msg;
    statusEl.className = "status show " + type;
  }
  function clearStatus() {
    statusEl.className = "status";
    statusEl.textContent = "";
  }

  function dataType() {
    const el = document.querySelector('input[name="data_type"]:checked');
    return el ? el.value : "log₂(TPM + 1)";
  }

  // Dropzone
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("drag");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      selectedFile = e.dataTransfer.files[0];
      pendingDemo = null;
      fileName.textContent = selectedFile.name;
    }
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) {
      selectedFile = fileInput.files[0];
      pendingDemo = null;
      fileName.textContent = selectedFile.name;
    }
  });

  document.querySelectorAll("[data-demo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      pendingDemo = btn.getAttribute("data-demo");
      selectedFile = null;
      fileInput.value = "";
      fileName.textContent =
        pendingDemo === "train"
          ? "Demo: X_train_for_app.csv"
          : "Demo: test_depmap_for_app.csv";
      runPredict();
    });
  });

  btnPredict.addEventListener("click", runPredict);
  btnExplain.addEventListener("click", () => explainSample(sampleSelect.value));
  sampleSelect.addEventListener("change", () => {
    if (sampleSelect.value) explainSample(sampleSelect.value);
  });

  async function runPredict() {
    if (!selectedFile && !pendingDemo) {
      setStatus("Upload a CSV or choose a demo.", "err");
      return;
    }
    clearStatus();
    btnPredict.classList.add("loading");
    btnPredict.disabled = true;

    const fd = new FormData();
    fd.append("data_type", dataType());
    if (pendingDemo) fd.append("demo", pendingDemo);
    else if (selectedFile) fd.append("file", selectedFile);

    try {
      const res = await fetch("/api/predict", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Prediction failed");
      lastResult = data;
      resultId = data.result_id;
      renderSummary(data.summary);
      renderTable(data.rows);
      renderCohort(data.cohort_img);
      fillSamples(data.samples);
      setStatus(
        `Predicted ${data.summary.n_samples} samples · ${data.summary.genes_mapped} genes mapped · ${data.summary.conversion}`,
        "ok"
      );
      // Auto-explain first sample
      if (data.samples && data.samples.length) {
        sampleSelect.value = data.samples[0];
        await explainSample(data.samples[0]);
      }
    } catch (err) {
      setStatus(err.message || String(err), "err");
    } finally {
      btnPredict.classList.remove("loading");
      btnPredict.disabled = false;
    }
  }

  function renderSummary(s) {
    const c = s.counts || {};
    const p = s.pcts || {};
    const epi = c.epithelial ?? c["epithelial-like"] ?? 0;
    const mid = c.hybrid ?? c.intermediate ?? c.transitioning ?? 0;
    const mes = c.mesenchymal ?? c["mesenchymal-like"] ?? 0;
    const pe = p.epithelial ?? p["epithelial-like"] ?? 0;
    const pm = p.hybrid ?? p.intermediate ?? p.transitioning ?? 0;
    const pM = p.mesenchymal ?? p["mesenchymal-like"] ?? 0;
    $("#kSamples").textContent = s.n_samples;
    $("#kConv").textContent = s.conversion;
    $("#kGenes").textContent = s.genes_mapped;
    $("#kMap").textContent = s.mapping_pct + "% coverage";
    $("#kEpi").textContent = epi;
    $("#kTra").textContent = mid;
    $("#kMes").textContent = mes;
    $("#kEpiP").textContent = pe + "%";
    $("#kTraP").textContent = pm + "%";
    $("#kMesP").textContent = pM + "%";
    $("#kConf").textContent = s.mean_confidence + "%";
  }

  function renderCohort(img) {
    const box = $("#cohortBox");
    box.innerHTML = img
      ? `<img src="${img}" alt="Cohort overview" />`
      : `<div class="placeholder">No plot</div>`;
  }

  function renderTable(rows) {
    if (!rows || !rows.length) {
      resultsBody.innerHTML =
        '<tr><td colspan="9" class="muted" style="text-align:center;padding:28px">No results</td></tr>';
      btnDownload.disabled = true;
      return;
    }
    resultsBody.innerHTML = rows
      .map(
        (r, i) => `
      <tr data-sample="${escapeAttr(r.sample)}" data-i="${i}">
        <td>${escapeHtml(r.sample)}</td>
        <td><span class="tag ${escapeAttr(r.state)}">${escapeHtml(r.state)}</span></td>
        <td>${fmt(r.E_z ?? r.E_score)}</td>
        <td>${fmt(r.M_z ?? r.M_score)}</td>
        <td>${fmt(r.EMT_axis_S ?? r.axis_S ?? r.EMT_score)}</td>
        <td>${r.confidence}%</td>
        <td>${r.p_epithelial ?? "—"}</td>
        <td>${r.p_hybrid ?? "—"}</td>
        <td>${r.p_mesenchymal ?? "—"}</td>
      </tr>`
      )
      .join("");

    resultsBody.querySelectorAll("tr[data-sample]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const s = tr.getAttribute("data-sample");
        sampleSelect.value = s;
        resultsBody.querySelectorAll("tr").forEach((x) => x.classList.remove("active"));
        tr.classList.add("active");
        explainSample(s);
      });
    });

    btnDownload.disabled = false;
    btnDownload.onclick = () => downloadCSV(rows);
  }

  function fillSamples(samples) {
    sampleSelect.innerHTML = samples
      .map((s) => `<option value="${escapeAttr(s)}">${escapeHtml(s)}</option>`)
      .join("");
    sampleSelect.disabled = !samples.length;
    btnExplain.disabled = !samples.length;
  }

  async function explainSample(sample) {
    if (!sample || !resultId) return;
    btnExplain.disabled = true;
    try {
      const res = await fetch("/api/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sample, result_id: resultId }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Explain failed");
      showDetail(data);
    } catch (err) {
      setStatus(err.message || String(err), "err");
    } finally {
      btnExplain.disabled = false;
    }
  }

  function showDetail(d) {
    const panel = $("#detailPanel");
    panel.classList.add("show");
    const tag = $("#dState");
    tag.textContent = d.state;
    tag.className = "tag " + d.state;
    $("#dSample").textContent = d.sample;
    $("#dConf").textContent = d.confidence + "%";
    const pr = d.probabilities || {};
    $("#dPe").textContent = (pr.epithelial ?? pr["epithelial-like"] ?? "—") + "%";
    $("#dPt").textContent = (pr.hybrid ?? pr.intermediate ?? "—") + "%";
    $("#dPm").textContent = (pr.mesenchymal ?? pr["mesenchymal-like"] ?? "—") + "%";
    $("#probBox").innerHTML = `<img src="${d.prob_img}" alt="Probabilities" />`;
    $("#shapBox").innerHTML = `<img src="${d.shap_img}" alt="SHAP drivers" />`;

    // highlight table row
    resultsBody.querySelectorAll("tr").forEach((tr) => {
      tr.classList.toggle("active", tr.getAttribute("data-sample") === d.sample);
    });
  }

  function downloadCSV(rows) {
    const cols = [
      "sample",
      "state",
      "E_z",
      "M_z",
      "EMT_axis_S",
      "EMT_score",
      "confidence",
      "p_epithelial",
      "p_hybrid",
      "p_mesenchymal",
    ];
    const lines = [cols.join(",")];
    rows.forEach((r) => {
      const flat = {
        ...r,
        E_z: r.E_z ?? r.E_score,
        M_z: r.M_z ?? r.M_score,
        EMT_axis_S: r.EMT_axis_S ?? r.axis_S ?? r.EMT_score,
        EMT_score: r.EMT_score ?? r.EMT_axis_S ?? r.axis_S,
      };
      lines.push(cols.map((c) => JSON.stringify(flat[c] ?? "")).join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "emtaxis_results.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function fmt(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(3) : String(v);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) {
    return String(s).replace(/"/g, "&quot;");
  }
})();
