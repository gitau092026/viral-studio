/* Viral Content Studio — client. Talks to the Flask pipeline, streams job
   progress, and enforces the human review gate before publish copy unlocks. */
(() => {
  "use strict";
  const $  = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const STAGES = ["research", "ideas", "create", "review", "publish"];
  const state = { review: null, approved: null, timer: null };

  const api = async (path, opts) => {
    const r = await fetch(path, opts);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
    return r.json();
  };
  const post = (path, body) =>
    api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const del = (path) => api(path, { method: "DELETE" });

  const toast = (msg, err = false) => {
    const t = $("#toast");
    t.textContent = msg; t.classList.toggle("err", err); t.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 3200);
  };
  const esc = (s) => (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const nfmt = (n) => (n || 0).toLocaleString("en-US");

  // ---- stage navigation ----------------------------------------------------
  function setActive(name) {
    $$(".stage").forEach(s => s.classList.toggle("active", s.dataset.stage === name));
    $$(".stage-panel").forEach(p => p.classList.toggle("active", p.dataset.panel === name));
    const i = STAGES.indexOf(name);
    $("#rail").style.setProperty("--rail-progress", `${(76 * i) / 4}%`);
  }
  function markDone(name, done = true) {
    const s = $$(".stage").find(x => x.dataset.stage === name);
    if (s) s.classList.toggle("done", done);
  }
  $$(".stage").forEach(s => s.addEventListener("click", () => setActive(s.dataset.stage)));

  // ---- job polling ---------------------------------------------------------
  function poll(jobId, onTick) {
    return new Promise((resolve, reject) => {
      const tick = async () => {
        try {
          const job = await api(`/api/jobs/${jobId}`);
          onTick && onTick(job);
          if (job.status === "done") return resolve(job.result);
          if (job.status === "error") return reject(new Error(job.error || "job failed"));
          setTimeout(tick, 650);
        } catch (e) { reject(e); }
      };
      tick();
    });
  }

  // ---- top-bar niche label -------------------------------------------------
  let hasNiche = true;   // optimistic until /api/status resolves; gates scanning
  async function loadStatus() {
    try {
      const s = await api("/api/status");
      hasNiche = !!(s.niche && s.niche.trim());
      $("#niche-tag").textContent = s.niche || "co-pilot";
      const nw = $("#niche-word"); if (nw) nw.textContent = s.niche || "your niche";
      if (!hasNiche) paintResearch();   // swap the empty state to the "set a niche" nudge
    } catch { /* status is best-effort */ }
  }

  // ---- SETTINGS (niche / keywords / voice) — the app's first modal ---------
  function openSettings() {
    $("#settings-save").disabled = true;
    $("#settings-backdrop").classList.add("show");
    loadSettings();
    setTimeout(() => { const n = $("#set-niche"); if (n) n.focus(); }, 40);
  }
  function closeSettings() { stopPreview(); $("#settings-backdrop").classList.remove("show"); }

  async function loadSettings() {
    try {
      const s = await api("/api/settings");
      $("#set-niche").value = s.niche || "";
      $("#set-keywords").value = (s.keywords || []).join(", ");
      const sel = $("#set-voice");
      sel.innerHTML = (s.voices || []).map(v =>
        `<option value="${esc(v.id)}"${v.id === s.voice ? " selected" : ""}>${esc(v.label)}</option>`).join("");
      if (s.voice && !(s.voices || []).some(v => v.id === s.voice)) {  // keep a hand-set voice selectable
        const o = document.createElement("option");
        o.value = s.voice; o.textContent = `${s.voice} (custom)`; o.selected = true;
        sel.appendChild(o);
      }
      $("#set-gemini-hint").style.display = s.gemini ? "none" : "flex";
    } catch (e) { toast(e.message, true); }
    validateSettings();
  }

  function validateSettings() {
    const niche = $("#set-niche").value.trim();
    const kw = $("#set-keywords").value.split(",").map(k => k.trim()).filter(Boolean);
    $("#settings-save").disabled = !(niche && kw.length);
  }

  async function saveSettings() {
    const niche = $("#set-niche").value.trim();
    const keywords = $("#set-keywords").value.split(",").map(k => k.trim()).filter(Boolean);
    const voice = $("#set-voice").value || "";
    if (!niche || !keywords.length) { toast("Add a niche and at least one keyword.", true); return; }
    const btn = $("#settings-save"); const html = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = `<span class="spin"></span><span>Saving…</span>`;
    try {
      const r = await post("/api/settings", { niche, keywords, voice });
      $("#niche-tag").textContent = r.niche || "co-pilot";
      const nw = $("#niche-word"); if (nw) nw.textContent = r.niche || "your niche";
      setScanAge(null);                 // caches cleared server-side — drop the freshness badge
      toast("Niche updated — re-scan for fresh trends");
      loadStatus(); loadResearch(); loadIdeas(); loadIdeasHint();
      closeSettings();
    } catch (e) {
      toast(e.message, true);
    } finally {
      btn.innerHTML = html; validateSettings();
    }
  }

  // ---- voice preview: hear the selected narrator before you render ---------
  // Raw fetch (not api()/post(), which assume JSON) — the endpoint streams mp3
  // bytes on success and JSON only on error. The button doubles as a stop while
  // a clip is playing.
  let previewAudio = null;
  function stopPreview() {
    if (previewAudio) { previewAudio.pause(); previewAudio = null; }
    const btn = $("#btn-voice-preview"); if (btn) btn.classList.remove("playing");
  }
  async function previewVoice() {
    if (previewAudio) { stopPreview(); return; }   // second click = stop
    const btn = $("#btn-voice-preview");
    const voice = $("#set-voice").value || "";
    const html = btn.innerHTML;
    const restore = () => { btn.disabled = false; btn.innerHTML = html; };
    btn.disabled = true;
    btn.innerHTML = `<span class="spin"></span><span class="vp-label">Synthesizing…</span>`;
    let r;
    try {
      r = await fetch("/api/voice/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
    } catch (e) {
      restore();
      toast(e.message || "Preview failed.", true);
      return;
    }
    // Synthesis done: free the button immediately (don't gate UI on playback
    // starting), then play. The button now doubles as a stop control.
    const url = URL.createObjectURL(await r.blob());
    restore();
    const done = () => { URL.revokeObjectURL(url); btn.classList.remove("playing"); previewAudio = null; };
    previewAudio = new Audio(url);
    previewAudio.addEventListener("ended", done);
    btn.classList.add("playing");
    previewAudio.play().catch(() => { done(); toast("Couldn't play the preview.", true); });
  }

  $("#btn-settings").addEventListener("click", openSettings);
  $("#settings-close").addEventListener("click", closeSettings);
  $("#settings-cancel").addEventListener("click", closeSettings);
  $("#settings-save").addEventListener("click", saveSettings);
  $("#set-niche").addEventListener("input", validateSettings);
  $("#set-keywords").addEventListener("input", validateSettings);
  $("#btn-voice-preview").addEventListener("click", previewVoice);
  $("#set-voice").addEventListener("change", stopPreview);  // don't keep playing the old voice
  $("#settings-backdrop").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeSettings(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("#settings-backdrop").classList.contains("show")) closeSettings();
  });

  // ---- RESEARCH ------------------------------------------------------------
  const RESEARCH_PAGE = 12;   // rows per page in the trends table
  let researchData = null;
  let researchPage = 0;

  function renderResearch(data) {
    researchData = data || { videos: [] };
    researchPage = 0;         // always land on page 1 for a fresh render / new scan
    paintResearch();
  }

  // YouTube thumbnails are deterministic from the video id, so we can show the
  // exact frame even for scans cached before the API started returning a URL.
  function ytId(v) {
    if (v.id) return v.id;
    const m = /[?&]v=([\w-]{6,})/.exec(v.url || "");
    return m ? m[1] : "";
  }
  function ytThumb(v) {
    const id = ytId(v);
    return id ? `https://i.ytimg.com/vi/${id}/hqdefault.jpg` : "";
  }

  function paintResearch() {
    const body = $("#research-body");
    const data = researchData || { videos: [] };
    const vids = data.videos || [];
    if (!hasNiche || !vids.length) {
      body.innerHTML = hasNiche
        ? `<div class="empty"><div class="big">No scan yet</div>
        <div>Run a scan to pull the fastest-climbing Shorts in your niche.<br>Needs the free YouTube API key.</div></div>`
        : `<div class="empty"><div class="big">Pick your niche to start</div>
        <div>Tell the studio what to research — a niche and a few keywords — then scan.</div>
        <button class="btn sm" data-open-settings style="margin-top:16px;"><span>Open Settings</span></button></div>`;
      return;
    }
    const total = vids.length;
    const pages = Math.ceil(total / RESEARCH_PAGE);
    researchPage = Math.min(Math.max(researchPage, 0), pages - 1);   // clamp
    const start = researchPage * RESEARCH_PAGE;
    const pageVids = vids.slice(start, start + RESEARCH_PAGE);
    const p = data.patterns || {};

    const cards = pageVids.map((v, i) => {
      const rank = start + i;                    // continuous global rank across pages
      const src = v.thumbnail || ytThumb(v);     // derive from the video id if the scan predates thumbnails
      // hqdefault is always present; fall back to mqdefault, then the gradient placeholder.
      const thumb = src
        ? `<img src="${esc(src)}" alt="" loading="lazy" referrerpolicy="no-referrer"
                data-fb="0" onerror="if(this.dataset.fb==='0'&&this.src.indexOf('hqdefault')>-1){this.dataset.fb='1';this.src=this.src.replace('hqdefault','mqdefault');}else{this.parentElement.classList.add('no-thumb');this.remove();}">`
        : "";
      return `
      <a class="trend-card${rank === 0 ? " rank-1" : ""}${thumb ? "" : " no-thumb"}" style="--i:${i}"
         href="${esc(v.url)}" target="_blank" rel="noopener" title="${esc(v.title)} — opens on YouTube">
        <div class="tc-thumb">
          ${thumb}
          <span class="tc-rank">${String(rank + 1).padStart(2, "0")}</span>
          <span class="tc-dur">${v.duration_s}s</span>
          <span class="tc-play" aria-hidden="true"></span>
        </div>
        <div class="tc-body">
          <div class="tc-vpd"><b>${nfmt(v.views_per_day)}</b><span>views/day</span></div>
          <div class="tc-title">${esc(v.title)}</div>
          <div class="tc-ch">${esc(v.channel)} · ${v.days_old}d old</div>
        </div>
      </a>`;
    }).join("");

    let pager = "";
    if (pages > 1) {
      const from = start + 1, to = start + pageVids.length;
      pager = `
          <div class="pager">
            <button class="btn sm ghost" data-nav="prev" ${researchPage === 0 ? "disabled" : ""}>‹ Prev</button>
            <span class="pager-info">${from}–${to} of ${total} · page ${researchPage + 1}/${pages}</span>
            <button class="btn sm ghost" data-nav="next" ${researchPage >= pages - 1 ? "disabled" : ""}>Next ›</button>
          </div>`;
    }

    const words = (p.title_words || []).slice(0, 14)
      .map(([w, n]) => `<span class="chip"><b>${esc(w)}</b> <span class="n">${n}</span></span>`).join("");
    const tags = (p.hashtags || []).slice(0, 12)
      .map(([t, n]) => `<span class="chip">${esc(t)} <span class="n">${n}</span></span>`).join("") || `<span class="hint">none detected</span>`;
    body.innerHTML = `
      <div class="trend-summary card">
        <div class="stat-row">
          <div class="stat"><div class="k vpd">${nfmt((pageVids[0] || {}).views_per_day || vids[0].views_per_day)}</div><div class="l">Top views/day</div></div>
          <div class="stat"><div class="k">${p.median_duration_s || 0}s</div><div class="l">Ideal length</div></div>
          <div class="stat"><div class="k">${p.sample_size || total}</div><div class="l">Analyzed</div></div>
        </div>
        <div class="trend-patterns">
          <div>
            <div class="section-label">Title words that keep winning</div>
            <div class="chips">${words}</div>
          </div>
          <div>
            <div class="section-label">Top hashtags</div>
            <div class="chips">${tags}</div>
          </div>
        </div>
        <div class="note"><span>💡</span><span>Study the top hooks, then say something <b>original</b> in that lane. Copying gets you demonetized — an original angle keeps you eligible.</span></div>
      </div>
      <div class="trend-cards">${cards}</div>
      ${pager}`;
  }

  // Shimmering placeholder grid shown while a scan is in flight — the fetch has a
  // face now instead of a lone button spinner.
  function renderResearchLoading() {
    const body = $("#research-body");
    const skel = Array.from({ length: 8 }, () => `
      <div class="trend-card skel">
        <div class="tc-thumb skel-box"></div>
        <div class="tc-body">
          <div class="skel-line w40"></div>
          <div class="skel-line w90"></div>
          <div class="skel-line w60"></div>
        </div>
      </div>`).join("");
    body.innerHTML = `
      <div class="scan-status"><span class="spin"></span><span>Scanning YouTube for view-velocity leaders…</span></div>
      <div class="trend-cards loading">${skel}</div>`;
  }

  // Pager clicks are delegated on the stable #research-body so they survive innerHTML rebuilds.
  $("#research-body").addEventListener("click", (e) => {
    if (e.target.closest("[data-open-settings]")) { openSettings(); return; }
    const btn = e.target.closest("[data-nav]");
    if (!btn || btn.disabled) return;
    researchPage += btn.dataset.nav === "next" ? 1 : -1;
    paintResearch();
  });
  // Freshness: cached scans are reused to save YouTube quota (search = 100 units;
  // 10k/day). Show how old the cache is; nudge a re-scan once it's stale (>24h).
  let scanAt = null;
  const STALE_MS = 24 * 3600 * 1000;
  function relAge(ms) {
    const s = Math.max(0, Math.round(ms / 1000));
    if (s < 45) return "just now";
    const m = Math.round(s / 60);
    if (m < 60) return m + "m ago";
    const h = Math.round(m / 60);
    if (h < 24) return h + "h ago";
    return Math.round(h / 24) + "d ago";
  }
  function renderScanAge() {
    const el = $("#research-when");
    if (!el) return;
    if (!scanAt) { el.textContent = ""; el.classList.remove("stale"); el.removeAttribute("title"); return; }
    const age = Date.now() - new Date(scanAt).getTime();
    const stale = age > STALE_MS;
    el.classList.toggle("stale", stale);
    el.title = "Last scan: " + new Date(scanAt).toLocaleString() + " — cached to save YouTube quota";
    el.textContent = stale ? `⚠ scanned ${relAge(age)} · re-scan for fresh trends` : `scanned ${relAge(age)}`;
  }
  function setScanAge(iso) { scanAt = iso || null; renderScanAge(); }

  async function loadResearch() {
    try {
      const d = await api("/api/trends");
      if (d.videos && d.videos.length) {
        renderResearch(d); markDone("research");
        setScanAge(d.generated_at);
      } else renderResearch({ videos: [] });
    } catch { renderResearch({ videos: [] }); }
  }
  $("#btn-research").addEventListener("click", async (e) => {
    if (!hasNiche) { toast("Pick a niche in Settings to start scanning.", true); openSettings(); return; }
    const btn = e.currentTarget; btn.disabled = true;
    btn.innerHTML = `<span class="spin"></span><span>Scanning…</span>`;
    renderResearchLoading();   // shimmer placeholders while the fetch runs
    try {
      const { job_id } = await post("/api/research");
      const res = await poll(job_id);
      renderResearch(res); markDone("research");
      setScanAge(res.generated_at || new Date().toISOString());
      toast(`Scanned ${res.videos.length} videos`);
      // Auto-advance: a finished scan carries you into Ideas (the trend table
      // stays on the Research tab). Mirrors render→Review / approve→Publish.
      // Stay put on an empty scan so you can re-run it.
      if (res.videos && res.videos.length) setActive("ideas");
    } catch (err) { toast(err.message, true); }
    finally { btn.disabled = false; btn.innerHTML = `<span>Scan YouTube</span>`; }
  });

  // ---- IDEAS ---------------------------------------------------------------
  function renderIdeas(ideas) {
    const body = $("#ideas-body");
    if (!ideas || !ideas.length) {
      body.innerHTML = `<div class="empty"><div class="big">No concepts yet</div>
        <div>Generate a batch of original angles from your trend scan.</div></div>`;
      return;
    }
    body.innerHTML = `<div class="ideas">` + ideas.map(it => `
      <div class="idea">
        <h3>${esc(it.title)}</h3>
        ${it.hook ? `<div class="hook">“${esc(it.hook)}”</div>` : ""}
        ${it.angle ? `<div class="angle">${esc(it.angle)}</div>` : ""}
        <div class="foot">
          <span class="tags">${esc((it.hashtags || []).slice(0, 3).join(" "))}</span>
          <button class="btn ghost sm" data-topic="${esc(it.title + (it.angle ? " — " + it.angle : ""))}">Send to Create →</button>
        </div>
      </div>`).join("") + `</div>`;
    $$("#ideas-body .idea .btn").forEach(b => b.addEventListener("click", () => sendToCreate(b.dataset.topic)));
  }
  async function loadIdeas() {
    try {
      const d = await api("/api/ideas");
      if (Array.isArray(d) && d.length) { renderIdeas(d); markDone("ideas"); }
      else renderIdeas([]);
    } catch { renderIdeas([]); }
  }
  $("#btn-ideas").addEventListener("click", async (e) => {
    const btn = e.currentTarget; btn.disabled = true;
    btn.innerHTML = `<span class="spin"></span><span>Thinking…</span>`;
    try {
      const brief = $("#ideas-brief") ? $("#ideas-brief").value.trim() : "";
      const { job_id } = await post("/api/ideas", { count: 8, brief });
      const res = await poll(job_id);
      renderIdeas(res); markDone("ideas");
      toast(`${res.length} concepts ready`);
    } catch (err) { toast(err.message, true); }
    finally { btn.disabled = false; btn.innerHTML = `<span>Generate concepts</span>`; }
  });

  // ---- CREATE --------------------------------------------------------------
  function sendToCreate(topic) {
    $("#topic").value = "";
    $("#picked-txt").textContent = topic;
    $("#picked").classList.add("show");
    $("#picked").dataset.topic = topic;
    setActive("create");
  }
  $("#picked-x").addEventListener("click", () => { $("#picked").classList.remove("show"); $("#picked").dataset.topic = ""; });

  // ---- render options (style / resolution / length target) -----------------
  let RENDER_OPTS = null;
  function pickerRow(label, name, items, selId) {
    return `<div class="picker-row">
      <div class="section-label">${esc(label)}</div>
      <div class="ship-modes">${items.map(it =>
        `<label class="radio"><input type="radio" name="${name}" value="${esc(String(it.id))}" ${String(it.id) === String(selId) ? "checked" : ""}><span>${esc(it.label)}</span></label>`).join("")}</div>
    </div>`;
  }
  async function loadRenderOptions() {
    const box = $("#render-options");
    if (!box) return;
    try { RENDER_OPTS = await api("/api/render-options"); } catch { return; }
    const d = RENDER_OPTS.defaults || {};
    box.innerHTML =
      pickerRow("Style", "opt-style", (RENDER_OPTS.styles || []), d.style) +
      pickerRow("Resolution", "opt-res", (RENDER_OPTS.resolutions || []), d.resolution) +
      pickerRow("Length (target)", "opt-dur", (RENDER_OPTS.durations || []).map(n => ({ id: n, label: `${n}s` })), d.duration);
  }
  function selectedRenderOptions() {
    const d = (RENDER_OPTS && RENDER_OPTS.defaults) || { style: "classic", resolution: "1080x1920", duration: 45 };
    const g = (name, fb) => { const el = $(`input[name="${name}"]:checked`); return el ? el.value : fb; };
    return { style: g("opt-style", d.style), resolution: g("opt-res", d.resolution), duration: Number(g("opt-dur", d.duration)) };
  }
  function styleLabel(id) {
    const s = ((RENDER_OPTS && RENDER_OPTS.styles) || []).find(x => x.id === id);
    return s ? s.label : (id || "");
  }

  const RENDER_STEPS = [
    ["script", "Writing the script"],
    ["voice", "Recording the voiceover"],
    ["broll", "Gathering b-roll"],
    ["captions", "Timing the captions"],
    ["assemble", "Assembling & burning captions"],
  ];
  // Step 1 of the generation chain (streamed by /api/compose/research).
  const CHAIN_STEPS = [
    ["derive", "Deriving search keywords"],
    ["research", "Reading live YouTube trends"],
    ["synthesize", "Synthesizing an original prompt"],
    ["compose_done", "Concept ready"],
  ];
  function paintSteps(activeKeys, stepDefs = RENDER_STEPS) {
    const seen = new Set(activeKeys);
    $("#steps").innerHTML = stepDefs.map(([k, label]) => {
      const idx = stepDefs.findIndex(s => s[0] === k);
      const lastSeen = stepDefs.reduce((acc, s, i) => seen.has(s[0]) ? i : acc, -1);
      const cls = seen.has(k) && idx < lastSeen ? "done"
                : (idx === lastSeen ? "active" : (activeKeys.includes("done") ? "done" : ""));
      return `<div class="step ${cls}"><span class="mk"></span>${label}</div>`;
    }).join("");
  }
  function startClock() {
    let s = 0; $("#tc").textContent = "00:00";
    state.timer = setInterval(() => {
      s++; $("#tc").textContent = `${String((s / 60) | 0).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    }, 1000);
  }
  function stopClock() { clearInterval(state.timer); state.timer = null; }

  // Shared render → review flow, used by the direct "Render draft" button and the
  // researched "Write the draft" button. payload goes straight to /api/make.
  async function runRender(payload, btn, restoreLabel) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spin"></span><span>Rendering…</span>`;
    $("#bay-empty").style.display = "none";
    $("#steps").style.display = "flex";
    paintSteps(["script"]); startClock();
    try {
      const { job_id } = await post("/api/make", payload);
      const res = await poll(job_id, (job) => paintSteps(job.steps.map(s => s.key)));
      paintSteps(["script", "voice", "broll", "captions", "assemble", "done"]);
      stopClock();
      toast(`Rendered “${res.title}” (${res.duration}s)`);
      markDone("create");
      await loadVideos(res.file);
      setActive("review");
    } catch (err) {
      stopClock(); toast(err.message, true);
      $("#bay-empty").style.display = "block";
      $("#bay-empty").querySelector(".big").textContent = "Render failed";
    } finally {
      btn.disabled = false; btn.innerHTML = restoreLabel;
    }
  }

  const currentInput = () =>
    $("#picked").classList.contains("show") ? $("#picked").dataset.topic : $("#topic").value.trim();

  // Direct path (unchanged behavior): render straight from the topic, no research.
  $("#btn-make").addEventListener("click", (e) =>
    runRender({ topic: currentInput(), ...selectedRenderOptions() }, e.currentTarget, `<span>Render draft</span>`));

  // ---- generation chain: research → editable prompt → draft ----------------
  let CONCEPT = null;   // last /api/compose/research result; drives "Write the draft"

  function renderConcept(res) {
    CONCEPT = res;
    const brief = res.brief || {};
    const badge = $("#concept-badge");
    if (res.used_llm && res.research_used) { badge.textContent = "AI + live research"; badge.className = "pill-badge ok"; }
    else if (res.used_llm) { badge.textContent = "AI-written"; badge.className = "pill-badge live"; }
    else { badge.textContent = "Template"; badge.className = "pill-badge review"; }

    const warn = $("#concept-warning");
    if (res.warning) { warn.textContent = res.warning; warn.style.display = "block"; }
    else { warn.style.display = "none"; warn.textContent = ""; }

    $("#concept-kws").innerHTML = (res.keywords || []).map(k => `<span class="kw">${esc(k)}</span>`).join("")
      || `<span class="kw muted">none</span>`;

    const r = res.research || {};
    const bits = [];
    if (r.sample_size) bits.push(`<span><b>${r.sample_size}</b> videos analyzed</span>`);
    if (r.median_duration_s) bits.push(`<span>~<b>${r.median_duration_s}s</b> median length</span>`);
    if ((r.title_words || []).length) bits.push(`<span>Recurring: ${r.title_words.slice(0, 8).map(esc).join(", ")}</span>`);
    if ((r.hashtags || []).length) bits.push(`<span>Tags: ${r.hashtags.slice(0, 8).map(esc).join(" ")}</span>`);
    let html = bits.length ? `<div class="trend-line">${bits.join("")}</div>` : "";
    if ((r.top_titles || []).length) {
      html += `<div class="trend-titles"><span class="tt-label">Real titles in this lane — study, don't copy:</span><ul>${
        r.top_titles.slice(0, 5).map(t => `<li>${esc(t)}</li>`).join("")}</ul></div>`;
    }
    $("#concept-trends").innerHTML = html
      || `<div class="trend-line muted">No live trend data — prompt synthesized from AI knowledge.</div>`;

    $("#concept-prompt").value = brief.prompt_text || "";
    $("#concept").style.display = "block";
    $("#concept").scrollIntoView({ behavior: "smooth", block: "nearest" });
    $("#concept-prompt").focus();
  }

  $("#btn-compose").addEventListener("click", async (e) => {
    const input = currentInput();
    if (!input) { toast("Tell me what the video should be about first.", true); $("#topic").focus(); return; }
    const btn = e.currentTarget; btn.disabled = true;
    btn.innerHTML = `<span class="spin"></span><span>Researching…</span>`;
    $("#concept").style.display = "none";
    $("#bay-empty").style.display = "none";
    $("#steps").style.display = "flex";
    paintSteps(["derive"], CHAIN_STEPS); startClock();
    try {
      const { job_id } = await post("/api/compose/research", { input });
      const res = await poll(job_id, (job) => paintSteps(job.steps.map(s => s.key), CHAIN_STEPS));
      paintSteps(["derive", "research", "synthesize", "compose_done", "done"], CHAIN_STEPS);
      stopClock();
      renderConcept(res);
      toast(res.warning ? "Prompt ready (AI-synthesized) — edit it, then draft" : "Researched concept ready — edit it, then draft");
    } catch (err) {
      stopClock(); toast(err.message, true);
      $("#bay-empty").style.display = "block";
      $("#bay-empty").querySelector(".big").textContent = "Research failed";
    } finally {
      btn.disabled = false; btn.innerHTML = `<span>Research &amp; write a prompt</span>`;
    }
  });

  $("#btn-draft").addEventListener("click", (e) => {
    if (!CONCEPT) { toast("Run research first.", true); return; }
    const prompt = $("#concept-prompt").value.trim();
    if (!prompt) { toast("The prompt is empty — write something to draft from.", true); $("#concept-prompt").focus(); return; }
    const brief = CONCEPT.brief || {};
    const topic = (brief.working_title || CONCEPT.input || prompt).slice(0, 300);
    runRender({
      topic, prompt, input: CONCEPT.input, keywords: CONCEPT.keywords, research: CONCEPT.research,
      brief, used_llm: CONCEPT.used_llm, research_used: CONCEPT.research_used,
      ...selectedRenderOptions(),
    }, e.currentTarget, `<span>Write the draft →</span>`);
  });

  // ---- small utils ---------------------------------------------------------
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  const fmtDate = (s) => {
    if (!s) return "";
    try { const d = new Date(String(s).replace(" ", "T")); return isNaN(d) ? s : d.toLocaleString(); }
    catch { return s; }
  };

  // ---- REVIEW --------------------------------------------------------------
  const CHECKS = [
    "Hook lands in the first 1 second",
    "Says something with a genuine, original angle",
    "Captions are readable and synced",
    "No dead air — the energy stays up",
    "I edited at least one line so it's truly mine",
  ];
  let VIDEOS = [];

  // Persist the checklist to the server (authoritative gate). approved = all(checks).
  async function saveReview(file, checks) {
    try {
      const r = await post(`/api/review/${encodeURIComponent(file)}`, { checks });
      const v = VIDEOS.find(x => x.file === file);
      if (v) { v.checks = r.checks; v.approved = r.approved; }
      if (r.approved) state.approved = VIDEOS.find(x => x.file === file) || state.approved;
      return r;
    } catch (e) { toast(e.message, true); return null; }
  }

  // "How this draft was made" — provenance from the .brief.json sidecar. Present only
  // for research/prompt renders; direct renders have no source and show nothing.
  function srcBadge(v) {
    if (v.source === "ai-research") return `<span class="pill-badge ok">AI + live research</span>`;
    if (v.source === "ai") return `<span class="pill-badge live">AI-written</span>`;
    if (v.source === "template") return `<span class="pill-badge review">Template</span>`;
    return "";
  }
  function provenanceBlock(v) {
    if (!v.source) return "";
    const b = v.brief || {};
    const kws = (b.keywords || []).map(k => `<span class="kw">${esc(k)}</span>`).join("");
    const r = b.research || {};
    const rbits = [];
    if (r.sample_size) rbits.push(`${r.sample_size} videos analyzed`);
    if (r.median_duration_s) rbits.push(`~${r.median_duration_s}s median length`);
    const detail = (kws || rbits.length || b.edited_prompt) ? `<div class="prov-body">
        ${kws ? `<div class="kw-chips">${kws}</div>` : ""}
        ${rbits.length ? `<div class="prov-line">Live research: ${esc(rbits.join(" · "))}</div>` : ""}
        ${b.edited_prompt ? `<div class="prov-line">Prompt used:</div><div class="prov-prompt">${esc(b.edited_prompt)}</div>` : ""}
      </div>` : "";
    return `<details class="prov"><summary>How this draft was made ${srcBadge(v)}</summary>${detail}</details>`;
  }

  function renderReview() {
    const body = $("#review-body");
    if (!VIDEOS.length) {
      body.innerHTML = `<div class="empty"><div class="big">No renders to review</div>
        <div>Head to Create and render your first draft.</div>
        <button class="btn" onclick="">Go to Create</button></div>`;
      body.querySelector(".btn").addEventListener("click", () => setActive("create"));
      return;
    }
    const cur = (state.review && VIDEOS.find(v => v.file === state.review.file)) || VIDEOS[0];
    state.review = cur;
    const checks0 = Array.isArray(cur.checks) ? cur.checks : [];
    const sl = cur.style ? `${esc(styleLabel(cur.style))} · ` : "";
    const dims = `${cur.width || 1080}×${cur.height || 1920}`;
    const others = VIDEOS.filter(v => v.file !== cur.file);
    const badge = (v) => {
      const s = v.schedule;
      if (s && s.youtube_id) return `<span class="pill-badge live">${s.status === "public" ? "Public" : "Uploaded"}</span>`;
      if (s && s.status === "scheduled") return `<span class="pill-badge review">Scheduled</span>`;
      if (v.approved) return `<span class="pill-badge ok">Approved ✓</span>`;
      return `<span class="pill-badge">Draft</span>`;
    };
    const history = !others.length ? "" : `
      <div class="drafts-wrap">
      <div class="section-label">Your drafts · ${others.length}</div>
      <div class="drafts">${others.map(v => `
        <div class="draft-card" data-file="${esc(v.file)}">
          <div class="dc-thumb">${v.thumb ? `<img src="/media/${esc(v.thumb)}" alt="">` : ""}<span class="d">${v.duration}s</span></div>
          <div class="dc-body">
            <div class="dc-title">${esc(v.title)}</div>
            <div class="dc-meta">${v.width || 1080}×${v.height || 1920}</div>
            <div class="dc-foot">${badge(v)}
              <button class="trash" data-del="${esc(v.file)}" title="Delete draft" aria-label="Delete draft">
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V6"/><path d="M10 11v6M14 11v6"/></svg>
              </button>
            </div>
          </div>
        </div>`).join("")}</div></div>`;
    body.innerHTML = `
      <div class="review-grid">
        <div class="phone"><video src="/media/${esc(cur.file)}"${cur.thumb ? ` poster="/media/${esc(cur.thumb)}"` : ""} controls playsinline preload="metadata"></video></div>
        <div>
          <div class="review-title">${esc(cur.title)}</div>
          <div class="review-meta">${sl}${dims} · ${cur.duration}s · ${esc(cur.file)}</div>
          ${provenanceBlock(cur)}
          <div class="script-block">${esc(cur.script) || "No script file."}</div>
          <div class="gate">
            <div class="gh"><span class="dot"></span><h4>Human review gate</h4></div>
            <div class="sub">YouTube demonetizes mass-produced, templated content. Clear every box before you ship — your checks are saved on the server and enforced at upload.</div>
            <div id="checks">${CHECKS.map((c, i) =>
              `<label class="check"><input type="checkbox" data-i="${i}" ${checks0[i] ? "checked" : ""}><span>${esc(c)}</span></label>`).join("")}</div>
            <div class="gate-foot">
              <button class="btn go" id="approve"><span>Approve & prep upload</span></button>
              <span class="status-txt" id="gate-status"></span>
            </div>
          </div>
        </div>
      </div>
      ${history}`;
    // History: click a card to load it into the hero; trash to delete it.
    $$("#review-body .draft-card").forEach(c => c.addEventListener("click", (e) => {
      if (e.target.closest(".trash")) return;
      state.review = VIDEOS.find(v => v.file === c.dataset.file);
      renderReview();
      // Clicking a draft should play it. The player lives at the top of the grid,
      // so pull it into view and start playback (the click is the user gesture).
      const vid = $("#review-body .phone video");
      if (vid) {
        vid.scrollIntoView({ behavior: "smooth", block: "center" });
        vid.play().catch(() => {});
      }
    }));
    $$("#review-body .trash").forEach(b => b.addEventListener("click", (e) => {
      e.stopPropagation(); deleteDraft(b.dataset.del);
    }));
    const boxes = $$("#checks input");
    const debouncedSave = debounce((checks) => saveReview(cur.file, checks), 450);
    const refresh = (persist) => {
      const checks = boxes.map(b => b.checked);
      const n = checks.filter(Boolean).length;
      const all = n === CHECKS.length;
      $("#approve").disabled = !all;
      const st = $("#gate-status");
      st.textContent = all ? "Approved — saved ✓" : `${n} / ${CHECKS.length} checked`;
      st.classList.toggle("ready", all);
      markDone("review", all);
      if (persist) debouncedSave(checks);
    };
    boxes.forEach(b => b.addEventListener("change", () => refresh(true)));
    refresh(false);  // reflect persisted state without re-posting
    $("#approve").addEventListener("click", async () => {
      const checks = boxes.map(b => b.checked);
      const r = await saveReview(cur.file, checks);  // ensure persisted before we leave
      if (!r || !r.approved) { toast("Clear all five checks first.", true); return; }
      state.approved = VIDEOS.find(v => v.file === cur.file) || cur;
      markDone("review");
      renderPublish();
      loadSchedule();
      setActive("publish");
      toast("Approved — upload unlocked");
    });
  }

  // Delete a draft: confirm, remove on the server (mp4 + sidecars + DB rows), reload.
  async function deleteDraft(file) {
    if (!confirm("Delete this draft? This permanently removes the video and its files — it can't be undone.")) return;
    try {
      await del(`/api/videos/${encodeURIComponent(file)}`);
      if (state.review && state.review.file === file) state.review = null;
      if (state.approved && state.approved.file === file) state.approved = null;
      toast("Draft deleted");
      await loadVideos();
    } catch (e) { toast(e.message, true); }
  }

  async function loadVideos(selectFile) {
    try {
      VIDEOS = await api("/api/videos");
      if (selectFile) state.review = VIDEOS.find(v => v.file === selectFile) || state.review;
      if (VIDEOS.length) markDone("create");
      // keep the approved-video reference fresh (schedule/status changes after upload)
      if (state.approved) {
        const a = VIDEOS.find(v => v.file === state.approved.file);
        if (a) state.approved = a;
      } else {
        const appr = VIDEOS.find(v => v.approved);   // restore approval across a refresh
        if (appr) { state.approved = appr; markDone("review"); }
      }
      renderReview();
      renderPublish();
    } catch { VIDEOS = []; renderReview(); }
  }

  // ---- YOUTUBE CONNECTION --------------------------------------------------
  let YT = { configured: false, connected: false, channel: null };
  async function loadYouTubeStatus() {
    try { YT = await api("/api/youtube/status"); }
    catch { YT = { configured: false, connected: false, channel: null }; }
    renderYouTubeConn();
    renderPublish();  // the upload button's enabled state depends on YT.connected
  }
  function renderYouTubeConn() {
    const el = $("#yt-conn");
    if (!el) return;
    if (YT.connected) {
      el.className = "yt-conn on";
      el.innerHTML = `<span class="yt-dot on"></span><span>YouTube connected${YT.channel ? ` · <b>${esc(YT.channel)}</b>` : ""}</span>`;
    } else if (!YT.configured) {
      el.className = "yt-conn";
      el.innerHTML = `<span class="yt-dot"></span><span>YouTube not set up — drop <code>client_secret.json</code> in your secrets folder, then connect. See SETUP.md.</span>`;
    } else {
      el.className = "yt-conn";
      el.innerHTML = `<span class="yt-dot"></span><span>Not connected</span>
        <button class="btn ghost sm" id="btn-connect"><span>Connect YouTube</span></button>`;
      $("#btn-connect").addEventListener("click", connectYouTube);
    }
  }
  async function connectYouTube() {
    const btn = $("#btn-connect");
    if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spin"></span><span>Waiting for browser…</span>`; }
    try {
      const { job_id } = await post("/api/youtube/connect");
      const res = await poll(job_id);
      toast(`Connected: ${res.channel || "YouTube"}`);
    } catch (e) { toast(e.message, true); }
    finally { await loadYouTubeStatus(); }
  }

  // ---- PUBLISH -------------------------------------------------------------
  function copyBtn(text) {
    return `<button class="btn ghost sm cp" data-copy="${esc(text)}">Copy</button>`;
  }
  function defaultPublishAt() {
    const d = new Date(Date.now() + 60 * 60 * 1000);  // +1h, local
    d.setSeconds(0, 0);
    const p = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function shipControls(v) {
    const s = v.schedule || null;
    if (s && s.youtube_id) {
      return `<div class="ship card">
        <div class="ship-head"><h4>On YouTube</h4></div>
        <div class="ship-done">
          <span class="tagpill ${esc(s.status || "")}">${esc(s.status || "uploaded")}</span>
          <span class="hint">${esc(s.privacy || "")}${s.scheduled_for ? ` · goes public ${esc(fmtDate(s.scheduled_for))}` : ""}</span>
          ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a>` : ""}
        </div></div>`;
    }
    const label = YT.connected ? "Schedule upload" : "Connect YouTube first";
    return `<div class="ship card">
      <div class="ship-head"><h4>Upload to YouTube</h4>
        <span class="hint">Gated — only an approved draft reaches this button.</span></div>
      <div class="ship-modes">
        <label class="radio"><input type="radio" name="mode" value="schedule" checked><span>Schedule</span></label>
        <label class="radio"><input type="radio" name="mode" value="private"><span>Private now</span></label>
        <label class="radio"><input type="radio" name="mode" value="public"><span>Public now</span></label>
      </div>
      <div class="ship-when" id="ship-when">
        <label for="publish-at">Go public at</label>
        <input type="datetime-local" id="publish-at" />
        <span class="hint">Uploads Private now; YouTube flips it Public then — works with your PC off.</span>
      </div>
      <div class="ship-foot">
        <button class="btn go" id="btn-upload" ${YT.connected ? "" : "disabled"}><span>${label}</span></button>
        <span class="hint" id="ship-status"></span>
      </div></div>`;
  }
  function wireShip(v) {
    const modeInputs = $$('#publish-body input[name="mode"]');
    if (!modeInputs.length) return;  // already uploaded — no controls
    const whenBox = $("#ship-when"), uploadBtn = $("#btn-upload"), atInput = $("#publish-at");
    if (atInput) { atInput.value = defaultPublishAt(); atInput.min = defaultPublishAt(); }
    const curMode = () => (modeInputs.find(r => r.checked) || {}).value || "schedule";
    const syncMode = () => {
      const mode = curMode();
      if (whenBox) whenBox.style.display = mode === "schedule" ? "block" : "none";
      if (uploadBtn && YT.connected)
        uploadBtn.querySelector("span").textContent =
          mode === "schedule" ? "Schedule upload" : (mode === "public" ? "Upload public" : "Upload private");
    };
    modeInputs.forEach(r => r.addEventListener("change", syncMode));
    syncMode();
    if (uploadBtn) uploadBtn.addEventListener("click", async () => {
      const mode = curMode();
      const payload = { file: v.file, mode };
      if (mode === "schedule") {
        const dt = atInput && atInput.value;
        if (!dt) { toast("Pick a date & time to schedule.", true); return; }
        payload.publish_at = dt;  // datetime-local (local time); server converts to UTC
      }
      uploadBtn.disabled = true;
      uploadBtn.innerHTML = `<span class="spin"></span><span>Uploading…</span>`;
      const stEl = $("#ship-status");
      try {
        const { job_id } = await post("/api/publish/youtube", payload);
        const res = await poll(job_id, (job) => {
          const last = job.steps && job.steps[job.steps.length - 1];
          if (last && stEl) stEl.textContent = last.label;
        });
        toast(mode === "schedule" ? "Scheduled on YouTube ✓" : "Uploaded to YouTube ✓");
        await loadVideos(v.file);   // pull the new schedule row into state.approved
        await loadSchedule();
        renderPublish();
      } catch (e) {
        toast(e.message, true);
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = `<span>Try again</span>`;
      }
    });
  }
  function renderPublish() {
    const body = $("#publish-body");
    if (!body) return;
    const v = state.approved;
    if (!v || !v.meta) {
      body.innerHTML = `<div class="empty"><div class="big">Nothing approved yet</div>
        <div>Approve a draft in Review to unlock upload + platform copy here.</div></div>`;
      return;
    }
    const m = v.meta, yt = m.youtube || {};
    const card = (badge, cls, name, inner) => `
      <div class="plat"><div class="plat-head"><span class="badge ${cls}">${badge}</span><h4>${name}</h4></div>
        <div class="copybox">${inner}</div></div>`;
    body.innerHTML = `
      <div class="review-title" style="margin-bottom:16px;">${esc(v.title)}</div>
      ${shipControls(v)}
      <div class="section-label">Or post by hand — copy per platform</div>
      ${card("YT", "yt", "YouTube Shorts", `
        ${copyBtn(`${yt.title}\n\n${yt.description}`)}
        <div class="field">Title</div><div class="val">${esc(yt.title)}</div>
        <div class="field">Description</div><pre>${esc(yt.description)}</pre>
        <div class="field">Tags</div><div class="val" style="font-family:var(--font-mono);font-size:12.5px;color:var(--muted);">${esc((yt.tags || []).join(", "))}</div>`)}
      ${card("TT", "tt", "TikTok", `${copyBtn(m.tiktok?.caption || "")}<pre>${esc(m.tiktok?.caption || "")}</pre>`)}
      ${card("FB", "fb", "Facebook / Reels", `${copyBtn(m.facebook?.caption || "")}<pre>${esc(m.facebook?.caption || "")}</pre>`)}
      ${card("IG", "ig", "Instagram Reels", `${copyBtn(m.instagram?.caption || "")}<pre>${esc(m.instagram?.caption || "")}</pre>`)}
      <div class="note"><span>🛡️</span><span>Automated upload is <b>gated on the review checklist</b> and defaults to Private/Scheduled — never mass-auto-publishing. Manual copy stays as a fallback.</span></div>`;
    wireShip(v);
    $$("#publish-body .cp").forEach(b => b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); toast("Copied to clipboard"); }
      catch { toast("Copy failed — select manually", true); }
    }));
  }

  // ---- SCHEDULE / QUEUE ----------------------------------------------------
  async function loadSchedule() {
    const el = $("#schedule-card");
    if (!el) return;
    let rows = [];
    try { rows = await api("/api/schedule"); } catch { rows = []; }
    if (!rows.length) {
      el.innerHTML = `<div class="section-label">Upload queue</div>
        <div class="mini-empty">Nothing uploaded or scheduled yet.</div>`;
      return;
    }
    const body = rows.map(r => `
      <tr>
        <td class="ttl">${esc(r.title || r.file)}</td>
        <td><span class="tagpill ${esc(r.status || "")}">${esc(r.status || "")}</span></td>
        <td>${esc(r.privacy || "—")}</td>
        <td>${r.scheduled_for ? esc(fmtDate(r.scheduled_for)) : "—"}</td>
        <td>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">open ↗</a>` : "—"}</td>
      </tr>`).join("");
    el.innerHTML = `
      <div class="section-label">Upload queue</div>
      <div class="card" style="padding:6px 10px;">
        <table class="q-table">
          <thead><tr><th>Video</th><th>Status</th><th>Privacy</th><th>Goes public</th><th></th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  // ---- ANALYTICS (what's working) ------------------------------------------
  function wireRefreshStats() {
    const b = $("#btn-refresh-stats");
    if (!b) return;
    b.addEventListener("click", async () => {
      b.disabled = true; b.innerHTML = `<span class="spin"></span><span>Fetching…</span>`;
      try {
        const { job_id } = await post("/api/analytics/refresh");
        const res = await poll(job_id);
        toast(`Updated ${res.updated} video(s)`);
        await loadAnalytics();
        loadIdeasHint();
      } catch (e) {
        toast(e.message, true);
        b.disabled = false; b.innerHTML = `<span>Refresh stats</span>`;
      }
    });
  }
  async function loadAnalytics() {
    const el = $("#analytics-card");
    if (!el) return;
    let rows = [];
    try { rows = await api("/api/analytics"); } catch { rows = []; }
    const refreshBtn = `<button class="btn ghost sm" id="btn-refresh-stats"><span>Refresh stats</span></button>`;
    if (!rows.length) {
      el.innerHTML = `<div class="lead-head"><div class="section-label">What's working</div>${refreshBtn}</div>
        <div class="mini-empty">No analytics yet. Upload a public/unlisted video, then Refresh to pull views.</div>`;
      wireRefreshStats();
      return;
    }
    const body = rows.map((r, i) => {
      const url = r.youtube_id ? `https://youtu.be/${r.youtube_id}` : null;
      const name = r.title || r.file || r.youtube_id;
      return `<tr>
        <td class="rk">${String(i + 1).padStart(2, "0")}</td>
        <td class="ttl">${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(name)}</a>` : esc(name)}</td>
        <td class="num vpd">${nfmt(r.views)}</td>
        <td class="num">${r.views_per_day != null ? nfmt(r.views_per_day) : "—"}</td>
        <td class="num">${nfmt(r.likes)}</td>
        <td class="num">${nfmt(r.comments)}</td>
      </tr>`;
    }).join("");
    el.innerHTML = `
      <div class="lead-head"><div class="section-label">What's working</div>${refreshBtn}</div>
      <div class="card" style="padding:6px 10px;">
        <table class="q-table">
          <thead><tr><th>#</th><th>Video</th><th class="num">Views</th><th class="num">Views/day</th><th class="num">Likes</th><th class="num">Comments</th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
    wireRefreshStats();
  }

  // ---- IDEAS hint (read-only: what's landed before) ------------------------
  async function loadIdeasHint() {
    const el = $("#ideas-hint");
    if (!el) return;
    let rows = [];
    try { rows = await api("/api/analytics"); } catch { rows = []; }
    const top = rows.filter(r => (r.title || r.topic) && r.views).slice(0, 6);
    if (!top.length) { el.style.display = "none"; el.innerHTML = ""; return; }
    el.style.display = "block";
    el.innerHTML = `
      <div class="section-label">What's landed before — inspiration, not a template</div>
      <div class="chips">${top.map(r =>
        `<span class="chip"><b>${esc(r.title || r.topic)}</b> <span class="n">${nfmt(r.views)} views</span></span>`).join("")}</div>`;
  }

  // ---- boot ----------------------------------------------------------------
  loadStatus();
  loadResearch();
  loadIdeas();
  loadIdeasHint();
  loadRenderOptions();
  loadVideos();
  loadYouTubeStatus();
  loadSchedule();
  loadAnalytics();
  setActive("research");
  setInterval(renderScanAge, 60000);   // keep "scanned Xh ago" accurate + flip to amber at 24h
})();
