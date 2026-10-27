// 弦外前端：无构建、零依赖。路由：#/ 记录列表 · #/r/:id 详情 · #/todos 待办 · #/analyzers 分析器

const view = document.getElementById("view");
const banner = document.getElementById("banner");

const STATUS = { queued: "排队中", transcribing: "转写中", analyzing: "分析中", done: "已完成", error: "出错" };
const LEVEL = { info: "提示", notice: "留意", warning: "警示" };

let pollTimer = null;

// 说话人数：空 = 自动判断。单人讲座选 1 最准。
const SPEAKER_OPTIONS = [["", "自动"], ["1", "1 人（讲座、独白）"], ["2", "2 人"], ["3", "3 人"], ["4", "4 人"], ["5", "5 人"]];

function speakerSelect(id, value) {
  const v = value == null ? "" : String(value);
  return `<select id="${id}" class="select" title="说话人数">${SPEAKER_OPTIONS
    .map(([k, label]) => `<option value="${k}" ${k === v ? "selected" : ""}>${label}</option>`)
    .join("")}</select>`;
}

// ---------- 工具 ----------

async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtTime(ms) {
  if (ms == null) return "";
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function confText(c) {
  return c == null ? "" : `置信 ${Math.round(c * 100)}%`;
}

// ---------- 首页：录音 / 导入 / 列表 ----------

async function renderHome() {
  view.innerHTML = `
    <section class="capture">
      <button id="rec-btn" class="btn primary big">● 开始录音</button>
      <label class="btn big">导入音频<input id="file-input" type="file" accept="audio/*,video/*" hidden></label>
      <label class="spk-count">说话人数 ${speakerSelect("num-speakers", null)}</label>
      <p class="hint">录音或导入后会在本地自动转写、区分说话人，并生成日记、待办和沟通洞察。</p>
    </section>
    <section id="list" class="list"><p class="muted">加载中…</p></section>`;

  document.getElementById("file-input").onchange = (e) => {
    const f = e.target.files[0];
    if (f) upload(f, f.name);
  };
  setupRecorder(document.getElementById("rec-btn"));
  await refreshList();
}

async function refreshList() {
  const el = document.getElementById("list");
  if (!el) return;
  const recs = await api("/recordings");
  if (!recs.length) {
    el.innerHTML = `<p class="muted empty">还没有记录。录一段对话，或者导入手机里的录音试试。</p>`;
    return;
  }
  el.innerHTML = recs
    .map((r) => `
      <a class="card rec" href="#/r/${r.id}">
        <div class="rec-title">${esc(r.title || r.filename || "未命名录音")}</div>
        <div class="rec-meta">
          <span>${esc(r.created_at)}</span>
          ${r.duration_ms ? `<span>${fmtTime(r.duration_ms)}</span>` : ""}
          <span class="status s-${r.status}">${STATUS[r.status] || r.status}</span>
          ${r.warnings ? `<span class="tag warning">${r.warnings} 条警示</span>` : ""}
          ${r.open_todos ? `<span class="tag">${r.open_todos} 项待办</span>` : ""}
        </div>
      </a>`)
    .join("");
  schedulePoll(recs.some((r) => !["done", "error"].includes(r.status)), refreshList);
}

function setupRecorder(btn) {
  if (!navigator.mediaDevices?.getUserMedia) {
    btn.disabled = true;
    btn.title = "浏览器录音需要 HTTPS 或 localhost，可以先用「导入音频」";
    return;
  }
  let recorder = null;
  let started = 0;
  let tick = null;
  btn.onclick = async () => {
    if (recorder) {
      recorder.stop();
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      showBanner(`无法使用麦克风：${e.message}`);
      return;
    }
    const chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      clearInterval(tick);
      const type = recorder.mimeType || "audio/webm";
      const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      recorder = null;
      btn.classList.remove("recording");
      btn.textContent = "● 开始录音";
      upload(new Blob(chunks, { type }), `录音-${new Date().toLocaleString("zh-CN")}.${ext}`);
    };
    recorder.start(1000);
    started = Date.now();
    btn.classList.add("recording");
    tick = setInterval(() => (btn.textContent = `■ 停止 ${fmtTime(Date.now() - started)}`), 500);
    btn.textContent = "■ 停止 00:00";
  };
}

async function upload(blob, filename) {
  const fd = new FormData();
  fd.append("file", blob, filename);
  const n = document.getElementById("num-speakers")?.value;
  if (n) fd.append("num_speakers", n);
  try {
    const rec = await api("/recordings", { method: "POST", body: fd });
    location.hash = `#/r/${rec.id}`;
  } catch (e) {
    showBanner(`上传失败：${e.message}`);
  }
}

// ---------- 详情页 ----------

async function renderRecording(id) {
  const r = await api(`/recordings/${id}`);
  const segByIdx = Object.fromEntries(r.segments.map((s) => [s.idx, s]));
  const nameOf = Object.fromEntries(r.speakers.map((s) => [s.speaker, s.name || s.speaker]));
  const speakerClass = Object.fromEntries(r.speakers.map((s, i) => [s.speaker, `spk-${i % 6}`]));
  const summaries = r.insights.filter((i) => i.kind === "summary");
  const insights = r.insights.filter((i) => i.kind === "insight").sort((a, b) => levelRank(b.level) - levelRank(a.level));
  const busy = !["done", "error"].includes(r.status);

  const evidence = (ids) =>
    ids?.length
      ? `<div class="evidence">${ids
          .map((n) => segByIdx[n])
          .filter(Boolean)
          .map((s) => `<button class="quote" data-seek="${s.start_ms}">#${s.idx} ${esc(nameOf[s.speaker])}：${esc(s.text)}</button>`)
          .join("")}</div>`
      : "";

  view.innerHTML = `
    <div class="detail-head">
      <a href="#/" class="back">← 返回</a>
      <h1>${esc(r.title || r.filename || "未命名录音")}</h1>
      <div class="rec-meta">
        <span>${esc(r.created_at)}</span>
        <span class="status s-${r.status}">${STATUS[r.status] || r.status}</span>
      </div>
      ${r.error ? `<div class="banner inline">${esc(r.error)}</div>` : ""}
      ${r.has_audio ? `<audio id="player" controls preload="metadata" src="/api/recordings/${id}/audio"></audio>` : ""}
      <div class="actions">
        <button class="btn" id="reanalyze" ${busy ? "disabled" : ""}>重新分析</button>
        ${r.has_audio ? `<span class="retranscribe">${speakerSelect("detail-speakers", r.num_speakers)}
          <button class="btn" id="retranscribe" ${busy ? "disabled" : ""}>重新转写</button></span>` : ""}
        <button class="btn danger" id="delete">删除</button>
      </div>
    </div>

    ${busy ? `<p class="muted">正在${STATUS[r.status]}，页面会自动刷新…</p>` : ""}

    ${r.speakers.length ? `
    <section>
      <h2>说话人 <small>点击标注身份，标注后「重新分析」结果更准</small></h2>
      <div class="speakers">
        ${r.speakers.map((s) => `<button class="chip ${speakerClass[s.speaker]}" data-speaker="${s.speaker}">${esc(s.name || s.speaker)}</button>`).join("")}
      </div>
    </section>` : ""}

    ${summaries.map((s) => `
      <section class="card summary">
        <h2>${esc(s.title || "日记")}</h2>
        <p class="pre">${esc(s.detail)}</p>
        ${evidence(s.evidence)}
      </section>`).join("")}

    ${insights.length ? `
    <section>
      <h2>弦外之音</h2>
      ${insights.map((i) => `
        <div class="card insight lv-${i.level} ${i.confidence != null && i.confidence < 0.5 ? "low" : ""}">
          <div class="insight-head">
            <span class="tag ${i.level}">${LEVEL[i.level] || i.level}</span>
            <strong>${esc(i.title)}</strong>
            <span class="muted small">${confText(i.confidence)}</span>
          </div>
          <p class="pre">${esc(i.detail)}</p>
          ${evidence(i.evidence)}
          <div class="feedback">
            <button class="icon ${i.feedback === "up" ? "on" : ""}" data-fb="${i.id}" data-v="up" title="说得对">👍</button>
            <button class="icon ${i.feedback === "down" ? "on" : ""}" data-fb="${i.id}" data-v="down" title="判断有误">👎</button>
          </div>
        </div>`).join("")}
    </section>` : ""}

    ${r.todos.length ? `
    <section>
      <h2>待办</h2>
      ${r.todos.map(todoRow).join("")}
    </section>` : ""}

    <section>
      <h2>转写</h2>
      <div class="transcript">
        ${r.segments.map((s) => `
          <div class="seg" data-seek="${s.start_ms}">
            <span class="ts">${fmtTime(s.start_ms)}</span>
            <span class="who ${speakerClass[s.speaker]}">${esc(nameOf[s.speaker])}</span>
            <span class="text">${esc(s.text)}</span>
          </div>`).join("") || `<p class="muted">暂无</p>`}
      </div>
    </section>`;

  view.querySelectorAll("[data-seek]").forEach((el) => (el.onclick = () => seek(+el.dataset.seek)));
  view.querySelectorAll("[data-speaker]").forEach((el) => (el.onclick = () => renameSpeaker(id, el.dataset.speaker, el.textContent)));
  view.querySelectorAll("[data-fb]").forEach((el) => (el.onclick = async () => {
    const value = el.classList.contains("on") ? null : el.dataset.v;
    await api(`/insights/${el.dataset.fb}/feedback`, json("POST", { value }));
    renderRecording(id);
  }));
  bindTodoRows(() => renderRecording(id));
  document.getElementById("reanalyze").onclick = async () => {
    await api(`/recordings/${id}/analyze`, { method: "POST" });
    setTimeout(() => renderRecording(id), 300);
  };
  const retranscribe = document.getElementById("retranscribe");
  if (retranscribe) retranscribe.onclick = async () => {
    if (!confirm("按新的说话人数重新转写？说话人标注和分析结果会重新生成。")) return;
    const v = document.getElementById("detail-speakers").value;
    try {
      await api(`/recordings/${id}/transcribe`, json("POST", { num_speakers: v ? +v : null }));
    } catch (e) {
      showBanner(`重新转写失败：${e.message}`);
      return;
    }
    setTimeout(() => renderRecording(id), 300);
  };
  document.getElementById("delete").onclick = async () => {
    if (!confirm("删除这段录音及其所有分析结果？此操作不可恢复。")) return;
    await api(`/recordings/${id}`, { method: "DELETE" });
    location.hash = "#/";
  };

  schedulePoll(busy, () => renderRecording(id));
}

function levelRank(l) {
  return { warning: 2, notice: 1, info: 0 }[l] ?? 0;
}

function seek(ms) {
  const p = document.getElementById("player");
  if (!p) return;
  p.currentTime = ms / 1000;
  p.play();
}

async function renameSpeaker(recId, speaker, current) {
  const name = prompt(`给「${current}」标注身份（如：我、妈妈、老板），留空则取消标注：`, current === speaker ? "" : current);
  if (name === null) return;
  await api(`/recordings/${recId}/speakers/${encodeURIComponent(speaker)}`, json("PUT", { name }));
  renderRecording(recId);
}

// ---------- 待办 ----------

function todoRow(t) {
  const meta = [t.owner && `👤 ${esc(t.owner)}`, t.due && `⏰ ${esc(t.due)}`, confText(t.confidence)].filter(Boolean).join(" · ");
  const from = t.recording_title !== undefined && t.recording_id
    ? `<a class="muted small" href="#/r/${t.recording_id}">来自：${esc(t.recording_title || "录音")}</a>` : "";
  return `
    <div class="card todo ${t.done ? "done" : ""}">
      <label><input type="checkbox" data-todo="${t.id}" ${t.done ? "checked" : ""}> <span>${esc(t.title)}</span></label>
      ${t.detail ? `<p class="small">${esc(t.detail)}</p>` : ""}
      <div class="muted small">${meta} ${from}</div>
    </div>`;
}

function bindTodoRows(rerender) {
  view.querySelectorAll("[data-todo]").forEach((el) => (el.onchange = async () => {
    await api(`/todos/${el.dataset.todo}`, json("PATCH", { done: el.checked }));
    rerender();
  }));
}

async function renderTodos() {
  const todos = await api("/todos");
  const open = todos.filter((t) => !t.done);
  const done = todos.filter((t) => t.done);
  view.innerHTML = `
    <h1>待办 <small>${open.length} 项进行中</small></h1>
    ${open.map(todoRow).join("") || `<p class="muted empty">没有进行中的待办。</p>`}
    ${done.length ? `<details><summary>已完成（${done.length}）</summary>${done.map(todoRow).join("")}</details>` : ""}`;
  bindTodoRows(renderTodos);
}

// ---------- 分析器 ----------

async function renderAnalyzers() {
  const list = await api("/analyzers");
  const KIND = { summary: "日记摘要", todo: "待办", insight: "沟通洞察" };
  view.innerHTML = `
    <h1>分析器</h1>
    <p class="hint">每个分析器就是一个 YAML 文件。放进 <code>data/analyzers/</code> 即可添加或覆盖，欢迎到 GitHub 提交 PR 分享你的分析器。</p>
    ${list.map((a) => `
      <div class="card">
        <div class="insight-head"><strong>${esc(a.name)}</strong><span class="tag">${KIND[a.kind] || a.kind}</span>
          ${a.enabled ? "" : `<span class="tag">已停用</span>`}</div>
        <p class="small">${esc(a.description)}</p>
        <div class="muted small"><code>${esc(a.id)}</code> · v${a.version}</div>
      </div>`).join("")}`;
}

// ---------- 路由 ----------

function schedulePoll(active, fn) {
  clearTimeout(pollTimer);
  if (active) pollTimer = setTimeout(() => fn().catch(() => {}), 2000);
}

function showBanner(msg) {
  banner.textContent = msg;
  banner.hidden = !msg;
}

async function checkHealth() {
  try {
    const h = await api("/health");
    const tips = [];
    if (!h.llm_configured) tips.push("尚未配置大模型（XW_LLM_API_KEY），只会转写、不会生成分析结果。");
    if (h.asr_engine === "mock") tips.push("当前为演示模式（XW_ASR_ENGINE=mock），转写内容是固定的示例对话。");
    showBanner(tips.join(" "));
  } catch {
    showBanner("无法连接后端服务。");
  }
}

async function route() {
  clearTimeout(pollTimer);
  const hash = location.hash || "#/";
  const nav = hash.startsWith("#/todos") ? "todos" : hash.startsWith("#/analyzers") ? "analyzers" : "home";
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === nav));
  try {
    const m = hash.match(/^#\/r\/(\w+)/);
    if (m) await renderRecording(m[1]);
    else if (nav === "todos") await renderTodos();
    else if (nav === "analyzers") await renderAnalyzers();
    else await renderHome();
  } catch (e) {
    view.innerHTML = `<p class="muted">出错了：${esc(e.message)}</p>`;
  }
}

window.addEventListener("hashchange", route);
checkHealth();
route();
