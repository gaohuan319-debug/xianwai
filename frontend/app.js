// 弦外前端：无构建、零依赖。
// 路由：#/ 记录列表 · #/r/:id 详情 · #/todos 待办 · #/analyzers 分析器 · #/analyzers/new 新建规则 · #/analyzers/:id 编辑规则

const view = document.getElementById("view");
const banner = document.getElementById("banner");
const toastEl = document.getElementById("toast");
const sideList = document.getElementById("side-list");

const STATUS = { queued: "排队中", transcribing: "转写中", analyzing: "分析中", done: "已完成", error: "出错" };
const STEPS = [["queued", "排队"], ["transcribing", "转写"], ["analyzing", "分析"], ["done", "完成"]];
const LEVEL = { info: "提示", notice: "留意", warning: "警示" };
const LEVEL_RANK = { warning: 2, notice: 1, info: 0 };
const KIND = { summary: "日记摘要", todo: "待办", insight: "沟通洞察" };
const RULE_EXAMPLES = [
  "家里人找我借钱或让我做担保时提醒我",
  "老板提到加班或周末工作时提醒我",
  "讲座里老师建议家长在家做的事，帮我记下来",
];

let pollTimer = null;
let sideTimer = null;
let activeRecId = null;

// ---------- 图标（Lucide，ISC 许可） ----------

const ICONS = {
  mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/>',
  square: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  up: '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/>',
  down: '<path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
  plus: '<path d="M5 12h14M12 5v14"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  next: '<path d="m9 18 6-6-6-6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  done: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  sparkles: '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4M10 9H8M16 13H8M16 17H8"/>',
  edit: '<path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/>',
  play: '<path d="M6 3 20 12 6 21Z"/>',
};

const icon = (name) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;

// ---------- 工具 ----------

async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("；") : body.detail;
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const pad = (n) => String(n).padStart(2, "0");

function fmtTime(ms) {
  if (ms == null) return "";
  const s = Math.floor(ms / 1000);
  return s >= 3600 ? `${Math.floor(s / 3600)}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}` : `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
}

function fmtDuration(ms) {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s} 秒`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} 分钟` : `${Math.floor(m / 60)} 小时 ${m % 60} 分`;
}

function fmtDate(s) {
  const d = new Date(String(s).replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return s || "";
  const now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (diff === 0) return `今天 ${hm}`;
  if (diff === 1) return `昨天 ${hm}`;
  const md = `${d.getMonth() + 1}月${d.getDate()}日`;
  return d.getFullYear() === now.getFullYear() ? `${md} ${hm}` : `${d.getFullYear()}年${md}`;
}

const confText = (c) => (c == null ? "" : `置信 ${Math.round(c * 100)}%`);
const enabledIds = (list) => list.filter((a) => a.enabled).map((a) => a.id);

let toastTimer = null;
function toast(msg) {
  toastEl.textContent = msg;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toastEl.hidden = true), 4000);
}

function showBanner(msg) {
  banner.textContent = msg;
  banner.hidden = !msg;
}

// 页面内的确认框，替代浏览器自带的 confirm
function confirmDialog(title, msg, okLabel = "确定", danger = false) {
  const dlg = $("dialog");
  if (!dlg.showModal) return Promise.resolve(window.confirm(`${title}\n${msg}`));
  $("dialog-title").textContent = title;
  $("dialog-msg").textContent = msg;
  $("dialog-ok").textContent = okLabel;
  $("dialog-ok").className = `btn ${danger ? "danger-solid" : "primary"}`;
  dlg.returnValue = "";
  dlg.showModal();
  return new Promise((resolve) => dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true }));
}

// 说话人数：空 = 自动判断。单人讲座选 1 最准。
const SPEAKER_OPTIONS = [["", "自动判断"], ["1", "1 人（讲座、独白）"], ["2", "2 人"], ["3", "3 人"], ["4", "4 人"], ["5", "5 人"]];

function speakerSelect(id, value) {
  const v = value == null ? "" : String(value);
  return `<select id="${id}" class="select">${SPEAKER_OPTIONS
    .map(([k, label]) => `<option value="${k}" ${k === v ? "selected" : ""}>${label}</option>`)
    .join("")}</select>`;
}

// 要跑的功能：一组可切换的标签
function featureChips(id, list, checked) {
  return `<div id="${id}" class="fchips">${list
    .map((a) => `<label class="fchip" title="${esc(a.description)}"><input type="checkbox" value="${esc(a.id)}" ${checked.includes(a.id) ? "checked" : ""}>
      <span>${icon("check")}${esc(a.name)}</span></label>`)
    .join("")}</div>`;
}

const pickedIds = (id) => [...document.querySelectorAll(`#${id} input:checked`)].map((el) => el.value);

// 每个页面顶部的工具栏：标题、副标题、右侧操作。back 只在需要返回时给出
function toolbar({ title, sub = "", back = "", backMobileOnly = false, actions = "" }) {
  return `
    <header class="toolbar">
      ${back ? `<a class="tb-back ${backMobileOnly ? "mobile-only" : ""}" href="${back}" aria-label="返回">${icon("back")}</a>` : ""}
      <div class="tb-title"><h1>${title}</h1>${sub ? `<div class="tb-sub">${sub}</div>` : ""}</div>
      <div class="tb-actions">${actions}</div>
    </header>`;
}

// 录音列表的一行：桌面上在侧边栏，手机上在「记录」页
function recItemHtml(r) {
  const busy = !["done", "error"].includes(r.status);
  const dot = busy ? `<i class="dot busy"></i>` : r.status === "error" ? `<i class="dot err"></i>` : r.warnings ? `<i class="dot warn"></i>` : "";
  const extra = busy ? STATUS[r.status] : r.status === "error" ? "处理出错" : r.warnings ? `${r.warnings} 条警示` : r.duration_ms ? fmtDuration(r.duration_ms) : "";
  return `
    <a class="side-rec ${r.id === activeRecId ? "active" : ""}" href="#/r/${r.id}">
      <span class="side-rec-title">${esc(r.title || r.filename || "未命名录音")}</span>
      <span class="side-rec-meta">${dot}${fmtDate(r.created_at)}${extra ? ` · ${extra}` : ""}</span>
    </a>`;
}

async function refreshSidebar() {
  clearTimeout(sideTimer);
  const [recs, todos] = await Promise.all([api("/recordings"), api("/todos?done=false")]);
  sideList.innerHTML = recs.map(recItemHtml).join("") || `<p class="side-empty">还没有录音</p>`;
  $("todo-count").textContent = todos.length || "";
  const mList = $("m-list");
  if (mList) mList.innerHTML = recs.length ? recs.map(recItemHtml).join("") : `<p class="fine empty">还没有录音</p>`;
  if (recs.some((r) => !["done", "error"].includes(r.status))) {
    sideTimer = setTimeout(() => refreshSidebar().catch(() => {}), 3000);
  }
  return recs;
}

function splitSummary(detail) {
  const lines = (detail || "").split("\n");
  return {
    body: lines.filter((l) => !l.startsWith("· ")).join("\n").trim(),
    highlights: lines.filter((l) => l.startsWith("· ")).map((l) => l.slice(2)),
  };
}

// 结论引用的原话。ctx 来自 transcriptCtx()
function quotesHtml(ids, ctx, max = 4, showMore = true) {
  const segs = (ids || []).map((n) => ctx.segByIdx[n]).filter(Boolean);
  if (!segs.length) return "";
  const more = showMore && segs.length > max ? `<span class="fine">另有 ${segs.length - max} 处原话</span>` : "";
  return `<div class="quotes">${segs.slice(0, max).map((s) => `
    <button class="quote ${ctx.spk[s.speaker]}" data-seek="${s.start_ms}" data-idx="${s.idx}">
      <span class="q-time">${fmtTime(s.start_ms)}</span><span class="q-who">${esc(ctx.nameOf[s.speaker])}</span><span>${esc(s.text)}</span>
    </button>`).join("")}${more}</div>`;
}

function transcriptCtx(r) {
  return {
    segByIdx: Object.fromEntries(r.segments.map((s) => [s.idx, s])),
    nameOf: Object.fromEntries(r.speakers.map((s) => [s.speaker, s.name || s.speaker])),
    spk: Object.fromEntries(r.speakers.map((s, i) => [s.speaker, `spk-${i % 6}`])),
  };
}

function diaryHtml(s, kicker = "日记") {
  const { body, highlights } = splitSummary(s.detail);
  return `
    <article class="card diary">
      <div class="kicker">${icon("file")}${kicker}</div>
      <h2>${esc(s.title || "今天的对话")}</h2>
      ${body ? `<p class="diary-body pre">${esc(body)}</p>` : ""}
      ${highlights.length ? `<ul class="highlights">${highlights.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : ""}
    </article>`;
}

function insightHtml(i, ctx, foot = "") {
  return `
    <article class="card insight lv-${i.level} ${i.confidence != null && i.confidence < 0.5 ? "low" : ""}">
      <div class="insight-head">
        <span class="level lv-${i.level}"><i></i>${LEVEL[i.level] || i.level}</span>
        <h3>${esc(i.title)}</h3>
      </div>
      ${i.detail ? `<p class="insight-detail pre">${esc(i.detail)}</p>` : ""}
      ${ctx ? quotesHtml(i.evidence, ctx) : ""}
      ${foot}
    </article>`;
}

function todoHtml(t, { showFrom = false, ctx = null, interactive = true } = {}) {
  const meta = [
    t.owner && `<span>${icon("user")}${esc(t.owner)}</span>`,
    t.due && `<span>${icon("clock")}${esc(t.due)}</span>`,
    t.confidence != null && t.confidence < 0.7 && `<span>不太确定</span>`,
    showFrom && t.recording_id && `<a href="#/r/${t.recording_id}">${icon("file")}${esc(t.recording_title || "录音")}</a>`,
  ].filter(Boolean).join("");
  return `
    <div class="todo ${t.done ? "done" : ""}">
      ${interactive ? `<label class="check" title="${t.done ? "标记为未完成" : "标记完成"}">
        <input type="checkbox" data-todo="${t.id}" ${t.done ? "checked" : ""}><span class="box">${icon("check")}</span></label>` : `<span class="check"><span class="box"></span></span>`}
      <div class="todo-body">
        <div class="todo-title">${esc(t.title)}</div>
        ${t.detail ? `<p class="todo-detail">${esc(t.detail)}</p>` : ""}
        ${meta ? `<div class="todo-meta">${meta}</div>` : ""}
        ${ctx ? quotesHtml(t.evidence, ctx, 1, false) : ""}
      </div>
      ${interactive ? `<button class="btn ghost icon-only danger" data-del-todo="${t.id}" title="删除这条待办">${icon("trash")}</button>` : ""}
    </div>`;
}

function bindTodoRows(rerender) {
  view.querySelectorAll("[data-todo]").forEach((el) => (el.onchange = async () => {
    await api(`/todos/${el.dataset.todo}`, json("PATCH", { done: el.checked }));
    rerender();
  }));
  view.querySelectorAll("[data-del-todo]").forEach((el) => (el.onclick = async () => {
    await api(`/todos/${el.dataset.delTodo}`, { method: "DELETE" });
    toast("已删除这条待办");
    rerender();
  }));
}

// ---------- 首页：录音 / 导入 / 列表 ----------

async function renderHome() {
  const list = await api("/analyzers");
  view.innerHTML = `
    ${toolbar({ title: "新录音", actions: `<label class="btn">${icon("upload")}导入音频<input id="file-input" type="file" accept="audio/*,video/*" hidden></label>` })}
    <div class="capture-page">
      <section class="capture" id="capture">
        <button id="rec-btn" class="record" aria-label="开始录音">${icon("mic")}</button>
        <h1 id="rec-title">录一段对话</h1>
        <p>点按钮开始录音，或者把音频文件拖到这里</p>
        <div class="card">
          <div class="group-row"><span class="row-label">说话人数</span>${speakerSelect("num-speakers", null)}</div>
          <div class="group-row"><span class="row-label">要跑的功能</span><div class="grow">${featureChips("home-picks", list, enabledIds(list))}</div></div>
        </div>
        <p class="fine">转写在本机完成，分析时只把文字发给你配置的大模型。功能都不选就只转写。</p>
      </section>
      <section class="m-list card mobile-only" id="m-list"></section>
    </div>`;

  $("file-input").onchange = (e) => {
    const f = e.target.files[0];
    if (f) upload(f, f.name);
  };
  setupRecorder($("rec-btn"));
  setupDrop($("capture"));
}

function setupRecorder(btn) {
  const title = $("rec-title");
  if (!navigator.mediaDevices?.getUserMedia) {
    btn.disabled = true;
    btn.title = "浏览器录音需要 HTTPS 或 localhost，可以先导入音频";
    title.textContent = "导入一段录音";
    return;
  }
  let recorder = null;
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
      toast(`无法使用麦克风：${e.message}`);
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
      btn.innerHTML = icon("mic");
      btn.setAttribute("aria-label", "开始录音");
      upload(new Blob(chunks, { type }), `录音-${new Date().toLocaleString("zh-CN")}.${ext}`);
    };
    recorder.start(1000);
    const started = Date.now();
    btn.classList.add("recording");
    btn.innerHTML = icon("square");
    btn.setAttribute("aria-label", "停止录音");
    const show = () => (title.innerHTML = `正在录音 <span class="rec-timer">${fmtTime(Date.now() - started)}</span>`);
    show();
    tick = setInterval(show, 500);
  };
}

function setupDrop(el) {
  el.addEventListener("dragover", (e) => {
    e.preventDefault();
    el.classList.add("dragging");
  });
  el.addEventListener("dragleave", (e) => {
    if (!el.contains(e.relatedTarget)) el.classList.remove("dragging");
  });
  el.addEventListener("drop", (e) => {
    e.preventDefault();
    el.classList.remove("dragging");
    const f = e.dataTransfer.files[0];
    if (f) upload(f, f.name);
  });
}

async function upload(blob, filename) {
  const fd = new FormData();
  fd.append("file", blob, filename);
  const n = $("num-speakers")?.value;
  if (n) fd.append("num_speakers", n);
  if ($("home-picks")) fd.append("analyzers", JSON.stringify(pickedIds("home-picks")));
  if ($("rec-title")) $("rec-title").textContent = "正在上传…";
  try {
    const rec = await api("/recordings", { method: "POST", body: fd });
    location.hash = `#/r/${rec.id}`;
  } catch (e) {
    if ($("rec-title")) $("rec-title").textContent = "录一段对话";
    toast(`上传失败：${e.message}`);
  }
}

// ---------- 详情页 ----------

async function renderRecording(id) {
  const [r, list] = await Promise.all([api(`/recordings/${id}`), api("/analyzers")]);
  const analyzerName = Object.fromEntries(list.map((a) => [a.id, a.name]));
  const ctx = transcriptCtx(r);
  const summaries = r.insights.filter((i) => i.kind === "summary");
  const insights = r.insights.filter((i) => i.kind === "insight")
    .sort((a, b) => LEVEL_RANK[b.level] - LEVEL_RANK[a.level] || (b.confidence ?? 0) - (a.confidence ?? 0));
  const busy = !["done", "error"].includes(r.status);
  const selected = r.analyzers ?? enabledIds(list);
  const ran = (kind) => !busy && r.segments.length && list.some((a) => a.kind === kind && selected.includes(a.id));
  const stepAt = STEPS.findIndex(([s]) => s === r.status);

  const insightFoot = (i) => `
    <div class="card-foot">
      <span class="fine">${[analyzerName[i.analyzer_id], confText(i.confidence)].filter(Boolean).map(esc).join(" · ")}</span>
      <div class="feedback">
        <button class="fb-btn ${i.feedback === "up" ? "on" : ""}" data-fb="${i.id}" data-v="up" title="说得对" aria-label="说得对">${icon("up")}</button>
        <button class="fb-btn ${i.feedback === "down" ? "on" : ""}" data-fb="${i.id}" data-v="down" title="判断有误" aria-label="判断有误">${icon("down")}</button>
      </div>
    </div>`;

  const sub = [fmtDate(r.created_at), r.duration_ms && fmtDuration(r.duration_ms), r.speakers.length && `${r.speakers.length} 位说话人`]
    .filter(Boolean).join(" · ");

  view.innerHTML = `
    ${toolbar({
      title: esc(r.title || r.filename || "未命名录音"), sub, back: "#/", backMobileOnly: true,
      actions: `<button class="btn ghost icon-only danger" id="delete" title="删除这段录音" aria-label="删除这段录音">${icon("trash")}</button>`,
    })}

    <div class="detail">
      <div class="detail-main">
        ${busy ? `
          <div class="card processing">
            <ol class="progress">${STEPS.map(([, label], i) => `<li class="${i < stepAt ? "done" : i === stepAt ? "current" : ""}"><span></span>${label}</li>`).join("")}</ol>
            <p class="fine">正在${STATUS[r.status]}，会自动刷新。长录音可能要几分钟。</p>
          </div>` : ""}
        ${r.error ? `<div class="notice warning">${icon("alert")}<span>${esc(r.error)}</span></div>` : ""}
        ${r.has_audio ? `<div class="card player"><audio id="player" controls preload="metadata" src="/api/recordings/${id}/audio"></audio></div>` : ""}

        ${r.speakers.length ? `
        <section>
          <div class="section-head"><h2>说话人</h2><span class="fine">点击标注身份，标注后重新分析会更准</span></div>
          <div class="speakers" id="speakers">
            ${r.speakers.map((s) => `<button class="spk-chip ${ctx.spk[s.speaker]} ${s.name ? "" : "unnamed"}" data-speaker="${s.speaker}" data-name="${esc(s.name || "")}">
              <span class="dot"></span>${esc(s.name || s.speaker)}</button>`).join("")}
          </div>
        </section>` : ""}

        ${summaries.map((s) => diaryHtml(s)).join("")}

        ${insights.length || ran("insight") ? `
        <section>
          <div class="section-head"><h2>弦外之音</h2><span class="fine">${insights.length ? `${insights.length} 条` : ""}</span></div>
          <div class="stack">
            ${insights.map((i) => insightHtml(i, ctx, insightFoot(i))).join("")
              || `<div class="card empty small">${icon("done")}没有发现需要特别留意的地方。</div>`}
          </div>
        </section>` : ""}

        ${r.todos.length || ran("todo") ? `
        <section>
          <div class="section-head"><h2>待办</h2><span class="fine">${r.todos.length ? `${r.todos.length} 项` : ""}</span></div>
          ${r.todos.length ? `<div class="card">${r.todos.map((t) => todoHtml(t, { ctx })).join("")}</div>`
            : `<div class="card empty small">${icon("done")}这段对话里没有提取到待办。</div>`}
        </section>` : ""}

        <details class="card options">
          <summary>${icon("refresh")}重新处理${icon("next").replace('class="ic"', 'class="ic chev"')}</summary>
          <div class="group-row">
            <span class="row-label">要跑的功能</span>
            <div class="grow">${featureChips("detail-picks", list, selected)}
              <div class="row" style="margin-top:10px">
                <button class="btn primary" id="reanalyze" ${busy ? "disabled" : ""}>重新分析</button>
                <span class="fine">只重跑勾选的功能，其余结果保留</span>
              </div>
            </div>
          </div>
          ${r.has_audio ? `
          <div class="group-row">
            <span class="row-label">说话人数</span>
            <div class="grow">
              <div class="row">${speakerSelect("detail-speakers", r.num_speakers)}
                <button class="btn" id="retranscribe" ${busy ? "disabled" : ""}>重新转写</button></div>
              <p class="fine" style="margin-top:6px">会重新区分说话人，已有的身份标注会清空</p>
            </div>
          </div>` : ""}
        </details>
      </div>

      <aside class="card detail-side">
        <div class="side-head"><h2>转写</h2><span class="fine">${r.segments.length ? `${r.segments.length} 段 · 点击从这里播放` : ""}</span></div>
        <div class="transcript" id="transcript">
          ${r.segments.map((s, i) => {
            const cont = i > 0 && r.segments[i - 1].speaker === s.speaker;
            return `<div class="seg ${ctx.spk[s.speaker]} ${cont ? "cont" : ""}" id="seg-${s.idx}" data-seek="${s.start_ms}" data-idx="${s.idx}">
              <span class="seg-time">${fmtTime(s.start_ms)}</span>
              <div><div class="seg-who"><i class="who-dot"></i>${esc(ctx.nameOf[s.speaker])}</div><p class="seg-text">${esc(s.text)}</p></div>
            </div>`;
          }).join("") || `<p class="empty fine">${busy ? "转写完成后会显示在这里" : "没有识别到语音内容"}</p>`}
        </div>
      </aside>
    </div>`;

  view.querySelectorAll("[data-seek]").forEach((el) => (el.onclick = () => seek(+el.dataset.seek, el.dataset.idx)));
  view.querySelectorAll("[data-speaker]").forEach((el) => (el.onclick = () => editSpeaker(id, el)));
  view.querySelectorAll("[data-fb]").forEach((el) => (el.onclick = async () => {
    const value = el.classList.contains("on") ? null : el.dataset.v;
    await api(`/insights/${el.dataset.fb}/feedback`, json("POST", { value }));
    el.parentElement.querySelectorAll(".fb-btn").forEach((b) => b.classList.toggle("on", b === el && value !== null));
    if (value) toast(value === "up" ? "谢谢，已记下这条判断是对的" : "谢谢，已记下这条判断有误");
  }));
  bindTodoRows(() => renderRecording(id));
  bindPlayer();

  $("reanalyze").onclick = async () => {
    try {
      await api(`/recordings/${id}/analyze`, json("POST", { analyzers: pickedIds("detail-picks") }));
    } catch (e) {
      return toast(`重新分析失败：${e.message}`);
    }
    view.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => renderRecording(id).then(refreshSidebar), 300);
  };
  const retranscribe = $("retranscribe");
  if (retranscribe) retranscribe.onclick = async () => {
    if (!(await confirmDialog("重新转写这段录音？", "会重新区分说话人并重新分析，已有的身份标注会清空。已完成的待办会保留。", "重新转写"))) return;
    const v = $("detail-speakers").value;
    try {
      await api(`/recordings/${id}/transcribe`, json("POST", { num_speakers: v ? +v : null }));
    } catch (e) {
      return toast(`重新转写失败：${e.message}`);
    }
    view.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => renderRecording(id).then(refreshSidebar), 300);
  };
  $("delete").onclick = async () => {
    if (!(await confirmDialog("删除这段录音？", "音频、转写和所有分析结果都会删除，无法恢复。", "删除", true))) return;
    await api(`/recordings/${id}`, { method: "DELETE" });
    toast("已删除");
    location.hash = "#/";
  };

  // 处理中每 2 秒刷新；保留滚动位置，避免页面跳回顶部
  schedulePoll(busy, async () => {
    const top = view.scrollTop;
    await renderRecording(id);
    view.scrollTop = top;
  });
}

// 点原话或转写：从那里开始播放，并在转写里高亮那一段
function seek(ms, idx) {
  const p = $("player");
  if (p) {
    p.currentTime = ms / 1000;
    p.play().catch(() => {});
  }
  const seg = idx && $(`seg-${idx}`);
  const box = $("transcript");
  if (!seg || !box) return;
  document.querySelectorAll(".seg.hit").forEach((s) => s.classList.remove("hit"));
  seg.classList.add("hit");
  box.scrollTo({ top: seg.offsetTop - box.clientHeight / 3, behavior: "smooth" });
}

// 播放时标出当前这一段
function bindPlayer() {
  const p = $("player");
  if (!p) return;
  const segs = [...document.querySelectorAll(".seg")].map((el) => ({ el, start: +el.dataset.seek }));
  let current = null;
  p.ontimeupdate = () => {
    const t = p.currentTime * 1000;
    let hit = null;
    for (const s of segs) {
      if (s.start > t) break;
      hit = s;
    }
    if (hit?.el !== current) {
      current?.classList.remove("now");
      hit?.el.classList.add("now");
      current = hit?.el ?? null;
    }
  };
}

// 原地标注说话人身份，输入时可以选已有的人物
async function editSpeaker(recId, chip) {
  const speaker = chip.dataset.speaker;
  const current = chip.dataset.name;
  const people = await api("/people").catch(() => []);
  let dl = $("people-list");
  if (!dl) {
    dl = document.createElement("datalist");
    dl.id = "people-list";
    document.body.append(dl);
  }
  dl.innerHTML = people.map((p) => `<option value="${esc(p.name)}">`).join("");

  const input = document.createElement("input");
  input.className = "input spk-input";
  input.value = current;
  input.placeholder = "如：我、妈妈、老板";
  input.setAttribute("list", "people-list");
  input.setAttribute("aria-label", `标注 ${speaker} 的身份`);
  chip.replaceWith(input);
  input.focus();
  input.select();

  let finished = false;
  const finish = async (save) => {
    if (finished) return;
    finished = true;
    const name = input.value.trim();
    if (save && name !== current) {
      await api(`/recordings/${recId}/speakers/${encodeURIComponent(speaker)}`, json("PUT", { name }));
      if (name) toast(`已标注为「${name}」。重新分析后，结果会用上这个身份`);
    }
    renderRecording(recId);
  };
  input.onkeydown = (e) => {
    if (e.key === "Enter") finish(true);
    if (e.key === "Escape") finish(false);
  };
  input.onblur = () => finish(true);
}

// ---------- 待办 ----------

async function renderTodos() {
  const todos = await api("/todos");
  const open = todos.filter((t) => !t.done);
  const done = todos.filter((t) => t.done);
  view.innerHTML = `
    ${toolbar({ title: "待办", sub: open.length ? `${open.length} 项进行中` : "" })}
    <div class="page narrow">
      ${open.length ? `<div class="card">${open.map((t) => todoHtml(t, { showFrom: true })).join("")}</div>`
        : `<div class="empty">${icon("done")}<div>没有进行中的待办</div><p class="fine">从对话里提取的承诺和约定会出现在这里</p></div>`}
      ${done.length ? `<details class="done-group"><summary>${icon("next")}已完成 ${done.length} 项</summary>
        <div class="card">${done.map((t) => todoHtml(t, { showFrom: true })).join("")}</div></details>` : ""}
    </div>`;
  bindTodoRows(() => renderTodos().then(refreshSidebar));
}

// ---------- 分析器 ----------

function analyzerRow(a) {
  return `
    <div class="group-row an-row">
      <div class="grow">
        <div class="row-label">${esc(a.name)}</div>
        <div class="row-desc">${esc(a.description)}</div>
        <div class="row-meta"><span class="pill">${KIND[a.kind] || a.kind}</span><span class="fine mono">${esc(a.id)} · v${a.version}</span></div>
      </div>
      ${a.custom ? `
        <a class="btn ghost icon-only" href="#/analyzers/${esc(a.id)}" title="编辑" aria-label="编辑">${icon("edit")}</a>
        <button class="btn ghost icon-only danger" data-del="${esc(a.id)}" data-name="${esc(a.name)}" title="删除" aria-label="删除">${icon("trash")}</button>` : ""}
      <label class="switch" title="默认启用"><input type="checkbox" data-enable="${esc(a.id)}" ${a.enabled ? "checked" : ""} aria-label="默认启用${esc(a.name)}"><span></span></label>
    </div>`;
}

async function renderAnalyzers() {
  const list = await api("/analyzers");
  const mine = list.filter((a) => a.custom);
  const builtin = list.filter((a) => !a.custom);
  view.innerHTML = `
    ${toolbar({ title: "分析器", sub: "打开开关的会默认用在新录音上",
      actions: `<a class="btn primary" href="#/analyzers/new">${icon("plus")}新建规则</a>` })}
    <div class="page narrow">
      <section class="section">
        <div class="section-head"><h2>我的规则</h2></div>
        ${mine.length ? `<div class="card">${mine.map(analyzerRow).join("")}</div>` : `
          <div class="card an-empty">${icon("sparkles")}
            <div><div class="row-label">用一句话，做一个自己的分析器</div>
              <div class="row-desc">比如「家里人找我借钱时提醒我」。弦外会把它变成提示词，你可以先试跑再保存。</div></div>
            <a class="btn" href="#/analyzers/new">新建规则</a>
          </div>`}
      </section>

      <section class="section">
        <div class="section-head"><h2>内置</h2></div>
        <div class="card">${builtin.map(analyzerRow).join("")}</div>
        <p class="fine" style="margin:10px 2px 0">高级用法：把 YAML 文件放进 <code>data/analyzers/</code> 也能添加分析器，欢迎到 GitHub 提交 PR 分享。</p>
      </section>
    </div>`;

  view.querySelectorAll("[data-enable]").forEach((el) => (el.onchange = async () => {
    try {
      await api(`/analyzers/${el.dataset.enable}`, json("PATCH", { enabled: el.checked }));
    } catch (e) {
      el.checked = !el.checked;
      toast(`设置失败：${e.message}`);
    }
  }));
  view.querySelectorAll("[data-del]").forEach((el) => (el.onclick = async () => {
    if (!(await confirmDialog(`删除「${el.dataset.name}」？`, "已经生成的结果会保留。", "删除", true))) return;
    await api(`/analyzers/${el.dataset.del}`, { method: "DELETE" });
    toast("已删除");
    renderAnalyzers();
  }));
}

// 新建或编辑自定义规则：一句话描述 → 生成提示词 → 修改 → 试跑 → 保存
async function renderRuleEditor(editId) {
  const [recs, existing] = await Promise.all([api("/recordings"), editId ? api(`/analyzers/${editId}`) : null]);
  const done = recs.filter((r) => r.status === "done");
  const d = existing || { kind: "insight" };
  const locked = editId ? "" : "locked";

  view.innerHTML = `
    ${toolbar({
      title: editId ? "编辑规则" : "新建规则", sub: "用一句话说出你想在对话里留意什么", back: "#/analyzers",
      actions: `<button class="btn primary" id="save" ${editId ? "" : "hidden"}>${editId ? "保存修改" : "保存并启用"}</button>`,
    })}
    <div class="page narrow">
      <ol class="steps">
        <li class="step">
          <div class="step-title"><span class="step-num">1</span>描述你关心的事</div>
          <div class="card step-content">
            <textarea id="rule" class="input" rows="3" maxlength="500" placeholder="例如：老板提到加班或周末工作时提醒我">${esc(d.rule)}</textarea>
            ${editId ? "" : `<div class="examples">${RULE_EXAMPLES.map((x) => `<button class="example" type="button">${esc(x)}</button>`).join("")}</div>`}
            <div class="row">
              <button class="btn" id="draft">${icon("sparkles")}${editId ? "重新生成提示词" : "生成提示词"}</button>
              <span class="fine">会调用一次大模型，这句描述会发给你配置的模型服务</span>
            </div>
          </div>
        </li>

        <li class="step ${locked}" id="step-2">
          <div class="step-title"><span class="step-num">2</span>查看并修改</div>
          <div class="card">
            <p class="step-hint">生成提示词之后，可以在这里修改</p>
            <div class="step-content">
              <div class="field-row">
                <label class="field"><span class="field-label">名称</span><input id="f-name" class="input" maxlength="20" value="${esc(d.name)}"></label>
                <label class="field"><span class="field-label">类型</span><select id="f-kind" class="select">${Object.entries(KIND)
                  .map(([k, v]) => `<option value="${k}" ${k === d.kind ? "selected" : ""}>${v}</option>`).join("")}</select></label>
              </div>
              <label class="field"><span class="field-label">说明</span><input id="f-desc" class="input" maxlength="200" value="${esc(d.description)}"></label>
              <label class="field"><span class="field-label">提示词</span><textarea id="f-prompt" class="input" rows="10" maxlength="4000">${esc(d.prompt)}</textarea></label>
              <p class="fine">只需写清楚要找什么、不要标什么。输出格式和引用原话的要求，系统会自动加上。</p>
            </div>
          </div>
        </li>

        <li class="step ${locked}" id="step-3">
          <div class="step-title"><span class="step-num">3</span>在一段录音上试跑</div>
          <div class="card">
            <p class="step-hint">满意了再保存</p>
            <div class="step-content">
              ${done.length ? `
                <div class="row">
                  <select id="t-rec" class="select">${done.map((r) => `<option value="${r.id}">${esc(r.title || r.filename || r.id)}</option>`).join("")}</select>
                  <button class="btn" id="try">${icon("play")}试跑</button>
                  <span class="fine">结果不会保存，每次试跑会调用一次大模型</span>
                </div>`
              : `<p class="fine">还没有处理完成的录音。可以先保存，之后在录音详情页选上这条规则运行。</p>`}
              <div id="t-out" class="preview"></div>
            </div>
          </div>
        </li>
      </ol>
    </div>`;

  const unlock = () => {
    ["step-2", "step-3"].forEach((s) => $(s).classList.remove("locked"));
    $("save").hidden = false;
  };
  const fields = () => ({
    name: $("f-name").value.trim(), kind: $("f-kind").value, description: $("f-desc").value.trim(),
    prompt: $("f-prompt").value.trim(), rule: $("rule").value.trim(),
  });
  const valid = (f) => {
    if (f.name && f.prompt) return true;
    toast("名称和提示词不能为空");
    (f.name ? $("f-prompt") : $("f-name")).focus();
    return false;
  };

  view.querySelectorAll(".example").forEach((el) => (el.onclick = () => {
    $("rule").value = el.textContent;
    $("rule").focus();
  }));

  $("draft").onclick = async () => {
    const rule = $("rule").value.trim();
    if (!rule) {
      toast("先用一句话描述你想留意什么");
      return $("rule").focus();
    }
    const btn = $("draft");
    btn.disabled = true;
    btn.innerHTML = `${icon("sparkles")}正在生成…`;
    try {
      const g = await api("/analyzers/draft", json("POST", { rule }));
      $("f-name").value = g.name;
      $("f-kind").value = g.kind;
      $("f-desc").value = g.description;
      $("f-prompt").value = g.prompt;
      unlock();
      $("step-2").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      toast(`生成失败：${e.message}`);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `${icon("sparkles")}重新生成提示词`;
    }
  };

  const tryBtn = $("try");
  if (tryBtn) tryBtn.onclick = async () => {
    const f = fields();
    if (!valid(f)) return;
    const recId = $("t-rec").value;
    tryBtn.disabled = true;
    $("t-out").innerHTML = `<p class="fine">正在试跑…</p>`;
    try {
      const [{ items }, rec] = await Promise.all([
        api("/analyzers/preview", json("POST", { ...f, recording_id: recId })),
        api(`/recordings/${recId}`),
      ]);
      $("t-out").innerHTML = previewHtml(f.kind, items, transcriptCtx(rec));
    } catch (e) {
      $("t-out").innerHTML = `<div class="notice warning">${icon("alert")}<span>试跑失败：${esc(e.message)}</span></div>`;
    } finally {
      tryBtn.disabled = false;
    }
  };

  $("save").onclick = async () => {
    const f = fields();
    if (!valid(f)) return;
    try {
      await api(editId ? `/analyzers/${editId}` : "/analyzers", json(editId ? "PUT" : "POST", f));
      toast(editId ? "已保存" : `已保存「${f.name}」，新录音会默认运行它`);
      location.hash = "#/analyzers";
    } catch (e) {
      toast(`保存失败：${e.message}`);
    }
  };
}

function previewHtml(kind, items, ctx) {
  if (kind === "summary") return diaryHtml(items[0], "试跑结果");
  if (!items.length) return `<div class="card empty small">${icon("done")}这段录音里没有找到符合规则的内容。</div>`;
  const head = `<p class="fine">找到 ${items.length} 条</p>`;
  if (kind === "todo") return `${head}<div class="card">${items.map((t) => todoHtml(t, { ctx, interactive: false })).join("")}</div>`;
  return head + items.map((i) => insightHtml(i, ctx, `<div class="card-foot"><span class="fine">${confText(i.confidence)}</span></div>`)).join("");
}

// ---------- 路由 ----------

function schedulePoll(active, fn) {
  clearTimeout(pollTimer);
  if (active) pollTimer = setTimeout(() => fn().catch(() => {}), 2000);
}

async function checkHealth() {
  try {
    const h = await api("/health");
    const tips = [];
    if (!h.llm_configured) tips.push("还没有配置大模型（XW_LLM_API_KEY），现在只会转写，不会生成分析结果。");
    if (h.asr_engine === "mock") tips.push("当前是演示模式（XW_ASR_ENGINE=mock），转写内容是固定的示例对话。");
    showBanner(tips.join(" "));
  } catch {
    showBanner("连不上后端服务，请确认服务已经启动。");
  }
}

async function route() {
  clearTimeout(pollTimer);
  const hash = location.hash || "#/";
  const nav = hash.startsWith("#/todos") ? "todos" : hash.startsWith("#/analyzers") ? "analyzers" : "home";
  const m = hash.match(/^#\/r\/(\w+)/);
  const am = hash.match(/^#\/analyzers\/(\w+)/);
  activeRecId = m ? m[1] : null;
  // 侧边栏里打开某段录音时，「新录音」不算选中；手机标签栏仍然停在「记录」
  document.querySelectorAll(".side-nav [data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === nav && !m));
  document.querySelectorAll(".tabbar [data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === nav));
  view.scrollTop = 0;
  try {
    if (m) await renderRecording(m[1]);
    else if (am) await renderRuleEditor(am[1] === "new" ? null : am[1]);
    else if (nav === "todos") await renderTodos();
    else if (nav === "analyzers") await renderAnalyzers();
    else await renderHome();
  } catch (e) {
    view.innerHTML = `<div class="empty">${icon("alert")}<div>页面加载失败</div><p class="fine">${esc(e.message)}</p></div>`;
  }
  refreshSidebar().catch(() => {});
}

window.addEventListener("hashchange", route);
checkHealth();
route();
