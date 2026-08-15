"use strict";

/* 操作画面（設計書7.1、7.3）。
   画面はAPIの上の薄い層にする。実行状態の正本は runs/ 配下のファイルなので、
   再読み込みしても過去の実行を選び直せば表示が復元できる。
   会話は実行完了後にまとめて表示する。1発言ずつ流すライブ表示は行わない。 */

const POLL_INTERVAL_MS = 1000;

const ROLE_LABELS = { werewolf: "人狼", villager: "村人" };
const WINNER_LABELS = { village: "村人陣営の勝ち", werewolf: "人狼陣営の勝ち" };
const PHASE_LABELS = {
  setup: "準備中",
  day_discussion: "昼の議論",
  vote: "投票",
  tie_break: "同数得票の決着",
  judge: "勝敗判定",
  finished: "終了",
  failed: "失敗",
};
const STATUS_LABELS = {
  queued: "受付済み（待機中）",
  running: "実行中",
  done: "完了",
  failed: "失敗",
  partial: "一部失敗",
};
const FUNCTION_LABELS = {
  Ne: "外向的直観", Ni: "内向的直観", Se: "外向的感覚", Si: "内向的感覚",
  Te: "外向的思考", Ti: "内向的思考", Fe: "外向的感情", Fi: "内向的感情",
};
// 要求定義書6.5。主機能からの候補。並びは mbti_types.py と揃える。
const DOMINANT_TO_MBTI = {
  Si: ["ISTJ", "ISFJ"], Ni: ["INFJ", "INTJ"], Ti: ["ISTP", "INTP"], Fi: ["ISFP", "INFP"],
  Se: ["ESTP", "ESFP"], Ne: ["ENFP", "ENTP"], Te: ["ESTJ", "ENTJ"], Fe: ["ESFJ", "ENFJ"],
};

const form = document.getElementById("config-form");
const startButton = document.getElementById("start-button");
const resetButton = document.getElementById("reset-button");
const formHint = document.getElementById("form-hint");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const statusDetail = document.getElementById("status-detail");
const progressBar = document.getElementById("progress-bar");
const errorBox = document.getElementById("error-box");
const resultPanel = document.getElementById("result-panel");
const runsList = document.getElementById("runs-list");
const runsHint = document.getElementById("runs-hint");

let pollTimer = null;
let activeJob = null;
let players = {};
let selectedRunId = null;

/* --- 共通 ------------------------------------------------------------- */

function esc(value) {
  return String(value === undefined || value === null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function api(path, options) {
  const response = await fetch(path, options);
  let body = null;
  try { body = await response.json(); } catch (e) { body = null; }
  if (!response.ok) {
    const detail = (body && body.detail) || response.statusText;
    throw new Error(detail);
  }
  return body;
}

function showError(message) {
  errorBox.hidden = !message;
  errorBox.textContent = message || "";
}

/* --- 設定パネル ------------------------------------------------------- */

function fillForm(config) {
  form.elements.player_count.value = config.player_count;
  form.elements.turn_count.value = config.turn_count;
  form.elements.game_count.value = config.game_count;
  form.elements.seed.value = config.seed;
  form.elements.role_assignment_mode.value = config.role_assignment_mode;
  form.elements.history_mode.value = config.history_mode;
  form.elements.werewolf_count.value = (config.role_composition || {}).werewolf || 1;
  form.elements.functions.value = (config.functions || []).join(", ");
  form.elements.provider.value = (config.brain || {}).provider || "stub";
  form.elements.model.value = (config.brain || {}).model || "";
  form.elements.max_output_chars.value = (config.brain || {}).max_output_chars || 200;
}

function readForm() {
  const playerCount = Number(form.elements.player_count.value);
  const werewolfCount = Number(form.elements.werewolf_count.value);
  const functions = form.elements.functions.value
    .split(/[,、\s]+/).map((s) => s.trim()).filter(Boolean);

  return {
    player_count: playerCount,
    turn_count: Number(form.elements.turn_count.value),
    game_count: Number(form.elements.game_count.value),
    seed: Number(form.elements.seed.value),
    role_assignment_mode: form.elements.role_assignment_mode.value,
    history_mode: form.elements.history_mode.value,
    role_composition: { werewolf: werewolfCount, villager: playerCount - werewolfCount },
    functions: functions,
    brain: {
      provider: form.elements.provider.value,
      model: form.elements.model.value.trim(),
      max_output_chars: Number(form.elements.max_output_chars.value),
    },
  };
}

function setFormEnabled(enabled) {
  Array.prototype.forEach.call(form.elements, (element) => {
    if (element !== resetButton) element.disabled = !enabled;
  });
  resetButton.disabled = enabled;
}

/* --- 状態表示 --------------------------------------------------------- */

function setStatus(status, detail, ratio) {
  statusDot.className = "dot" + (status ? " " + status : "");
  statusText.textContent = STATUS_LABELS[status] || "未実行";
  statusDetail.textContent = detail || "";
  progressBar.style.width = Math.round(Math.max(0, Math.min(1, ratio || 0)) * 100) + "%";
}

function runDetail(status) {
  const phase = PHASE_LABELS[status.phase] || status.phase || "";
  if (status.status === "running" && status.phase === "day_discussion") {
    return phase + " " + status.turn + " / " + status.turn_count + "ターン目";
  }
  return phase;
}

/* --- 実行 ------------------------------------------------------------- */

async function startRun(event) {
  event.preventDefault();
  showError("");
  let payload;
  try {
    payload = readForm();
  } catch (error) {
    showError("入力を確認してください: " + error.message);
    return;
  }

  startButton.disabled = true;
  try {
    const job = await api("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    activeJob = job;
    selectedRunId = job.run_id;
    setFormEnabled(false);
    formHint.textContent = "実行中は条件を変更できない。完了後に「条件を編集し直す」で戻せる。";
    resultPanel.hidden = true;
    setStatus("queued", "series_id: " + job.series_id, 0);
    startPolling();
  } catch (error) {
    startButton.disabled = false;
    showError(String(error.message || error));
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(poll, POLL_INTERVAL_MS);
  poll();
}

function stopPolling() {
  if (pollTimer !== null) clearInterval(pollTimer);
  pollTimer = null;
}

async function poll() {
  if (!activeJob) return stopPolling();
  try {
    if (activeJob.game_count > 1) {
      await pollSeries();
    } else {
      await pollSingleRun();
    }
  } catch (error) {
    showError(String(error.message || error));
  }
}

async function pollSingleRun() {
  const status = await api("/api/runs/" + encodeURIComponent(activeJob.run_id));
  const ratio = status.turn_count ? status.turn / status.turn_count : 0;
  setStatus(status.status, runDetail(status), ratio);

  if (status.status === "done" || status.status === "failed") {
    await finishJob(activeJob.run_id, status);
  }
}

async function pollSeries() {
  const series = await api("/api/series/" + encodeURIComponent(activeJob.series_id));
  const finished = (series.runs || []).length;
  const total = series.game_count || 1;
  const detail = finished + " / " + total + "試合" +
    (series.current_run_id ? "（実行中: " + series.current_run_id + "）" : "");
  const terminal = ["done", "failed", "partial"].indexOf(series.status) !== -1;
  setStatus(terminal ? series.status : "running", detail, finished / total);

  if (terminal) {
    const entries = series.runs || [];
    const last = entries[entries.length - 1];
    if (last) await finishJob(last.run_id, null);
    else await finishJob(activeJob.run_id, null);
  }
}

async function finishJob(runId, status) {
  stopPolling();
  activeJob = null;
  startButton.disabled = false;
  if (status && status.error) {
    showError("失敗（" + status.error.kind + "）: " + status.error.message);
  }
  await showRun(runId);
  await loadRuns();
}

/* --- 結果の表示 ------------------------------------------------------- */

async function showRun(runId) {
  selectedRunId = runId;
  let log;
  try {
    log = await api("/api/runs/" + encodeURIComponent(runId) + "/log");
  } catch (error) {
    showError("結果を読み込めなかった: " + String(error.message || error));
    return;
  }

  players = {};
  (log.players || []).forEach((p) => { players[p.player_id] = p; });

  if (log.status !== "done" && log.failure) {
    showError("失敗（" + log.failure.kind + "）: " + log.failure.message +
      "  到達フェーズ: " + (PHASE_LABELS[log.phase] || log.phase) +
      "。ここまでの会話は下に表示している。");
  }

  document.getElementById("result-cards").innerHTML = renderCards(log);
  document.getElementById("roster").innerHTML = renderRoster(log);
  document.getElementById("timeline").innerHTML = renderTimeline(log);
  document.getElementById("votes").innerHTML = renderVotes(log);
  document.getElementById("metrics").innerHTML = renderMetrics(log);
  document.getElementById("conditions").innerHTML = renderConditions(log);

  const dir = "/runs/" + log.series_id + "/r" + String(log.run_index).padStart(3, "0") + "/";
  document.getElementById("artifact-links").innerHTML =
    "出力ファイル: " +
    ['result.html', 'run_log.json', 'summary.md', 'timeline.md', 'metrics.csv']
      .map((name) => '<a href="' + dir + name + '" target="_blank">' + name + "</a>")
      .join(" / ");

  resultPanel.hidden = false;
  highlightSelected();
}

function mbtiOf(fn) {
  const types = DOMINANT_TO_MBTI[fn] || [];
  return types.length ? types.join(" / ") : "—";
}

// MBTIタイプが確定しているプレイヤー（v1改善のMVPロースター）はタイプ名を、
// 確定していない（旧ログ、functions直接指定など）場合は候補2タイプを表示する。
function identityOf(entry) {
  if (!entry) return "—";
  if (entry.mbti_type) {
    return entry.mbti_type + (entry.display_name ? "（" + entry.display_name + "）" : "");
  }
  return mbtiOf(entry.function);
}

function winningMbti(log) {
  const winner = (log.result || {}).winner;
  const wanted = winner === "werewolf" ? "werewolf" : (winner === "village" ? "villager" : "");
  if (!wanted) return "決着なし";
  const parts = (log.players || []).filter((p) => p.role === wanted)
    .map((p) => p.player_id + "（" + p.function + "）→ " + identityOf(p));
  return parts.join("、") || "—";
}

function who(id) {
  const p = players[id];
  if (!p) return esc(id || "—");
  const label = FUNCTION_LABELS[p.function] ? p.function + "／" + FUNCTION_LABELS[p.function] : p.function;
  return esc(id) + "（" + esc(label) + " / " + esc(ROLE_LABELS[p.role] || p.role) + " / " + esc(identityOf(p)) + "）";
}

function topOf(log, key) {
  const rows = (log.metrics && log.metrics.per_player) || [];
  if (!rows.length) return "—";
  const top = Math.max.apply(null, rows.map((r) => r[key] || 0));
  if (!top) return "該当なし";
  return rows.filter((r) => (r[key] || 0) === top)
    .map((r) => r.player_id + "（" + r.function + "）→ " + identityOf(r)).join("、") + " — " + top;
}

function renderRoster(log) {
  const list = log.players || [];
  if (!list.length) return "";
  const cards = list.map((p) => {
    const fn = FUNCTION_LABELS[p.function] ? p.function + "（" + FUNCTION_LABELS[p.function] + "）" : p.function;
    const stack = (p.function_stack || []).join(" / ");
    return '<div class="card"><div class="label">' + esc(p.player_id) + '・' + esc(ROLE_LABELS[p.role] || p.role) + '</div>'
      + '<div class="value">' + esc(identityOf(p)) + '</div>'
      + '<div class="sub">主機能 ' + esc(fn) + (stack ? '<br>スタック ' + esc(stack) : '') + '</div>'
      + '</div>';
  }).join("");
  return '<div class="cards">' + cards + '</div>';
}

function renderCards(log) {
  const result = log.result || {};
  const winnerClass = result.winner === "village" ? "village" : (result.winner === "werewolf" ? "werewolf" : "");
  const wolves = (log.players || []).filter((p) => p.role === "werewolf")
    .map((p) => p.player_id + "（" + p.function + "）→ " + identityOf(p)).join("、") || "—";
  const cards = [
    ["勝敗", '<span class="' + winnerClass + '">' + esc(WINNER_LABELS[result.winner] || "決着なし") + "</span>"],
    ["勝ったMBTI", esc(winningMbti(log))],
    ["人狼だったMBTI", esc(wolves)],
    ["処刑された人", result.executed ? who(result.executed) : "—"],
    ["最も疑われた人", esc(topOf(log, "suspected_by_count"))],
    ["最も発言した人", esc(topOf(log, "speech_count"))],
    ["決着方法", result.tie_break ? "同数得票のため " + esc(result.tie_break.method) : "最多得票が1人"],
  ];
  return cards.map((card) =>
    '<div class="card"><div class="label">' + esc(card[0]) + '</div><div class="value">' + card[1] + "</div></div>"
  ).join("");
}

function renderTimeline(log) {
  const turns = log.turns || [];
  if (!turns.length) return "<p class='muted'>発言はまだ記録されていない。</p>";
  let html = "";
  let current = null;
  turns.forEach((turn) => {
    if (turn.turn !== current) {
      current = turn.turn;
      html += '<div class="turn">ターン ' + esc(current) + " / " + esc((log.config || {}).turn_count) + "</div>";
    }
    const badges = [];
    if (turn.parse_failed) badges.push("形式が崩れた応答");
    if (turn.wait_seconds) badges.push(turn.wait_seconds + "秒");
    html += '<div class="speech"><div class="who">' + who(turn.player_id) +
      badges.map((b) => '<span class="badge">' + esc(b) + "</span>").join("") +
      "</div>" + esc(turn.speech_text) + "</div>";
  });
  return html;
}

function renderVotes(log) {
  const votes = log.votes || [];
  if (!votes.length) return "<p class='muted'>投票はまだ記録されていない。</p>";
  const counts = (log.result || {}).vote_counts || {};
  const tally = Object.keys(counts).map((k) => k + " " + counts[k] + "票").join("、");
  const rows = votes.map((vote) =>
    "<tr><td>" + who(vote.voter) + "</td><td>" + esc(vote.target) + "</td>" +
    '<td class="wrap">' + esc(vote.reason) + "</td><td>" +
    (vote.fallback ? "乱数で決定" : (vote.invalid_retry_count ? "再要求" + vote.invalid_retry_count + "回" : "—")) +
    "</td></tr>").join("");
  return (tally ? "<p class='muted'>得票: " + esc(tally) + "</p>" : "") +
    '<div class="scroll"><table><thead><tr><th>投票者</th><th>投票先</th>' +
    '<th class="wrap">理由</th><th>備考</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
}

function renderMetrics(log) {
  const rows = (log.metrics && log.metrics.per_player) || [];
  if (!rows.length) return "<p class='muted'>集計はない。</p>";
  const head = ["ID", "心理機能", "MBTI", "役職", "発言数", "平均文字数", "投票先", "勝敗",
    "疑い", "疑われ", "質問", "反論", "同調", "仮説"];
  const body = rows.map((row) => "<tr>" + [
    row.player_id,
    row.function + (FUNCTION_LABELS[row.function] ? "（" + FUNCTION_LABELS[row.function] + "）" : ""),
    identityOf(row),
    ROLE_LABELS[row.role] || row.role,
    row.speech_count, row.avg_chars, row.final_vote || "—",
    row.win === null || row.win === undefined ? "—" : (row.win ? "勝ち" : "負け"),
    row.suspicion_count, row.suspected_by_count, row.question_count,
    row.rebuttal_count, row.agreement_count, row.hypothesis_count,
  ].map((value) => "<td>" + esc(value) + "</td>").join("") + "</tr>").join("");
  return '<div class="scroll"><table><thead><tr>' +
    head.map((h) => "<th>" + esc(h) + "</th>").join("") +
    "</tr></thead><tbody>" + body + "</tbody></table></div>";
}

function renderConditions(log) {
  const config = log.config || {};
  const timing = log.timing || {};
  const brain = log.brain || {};
  const items = [
    ["run_id", log.run_id],
    ["series_id", log.series_id],
    ["参加人数", (config.player_count || "") + "人"],
    ["役職構成", Object.keys(config.role_composition || {})
      .map((k) => (ROLE_LABELS[k] || k) + (config.role_composition[k]) + "人").join("、")],
    ["議論ターン数", config.turn_count],
    ["seed", config.seed],
    ["base_seed", config.base_seed],
    ["役職割当方式", config.role_assignment_mode],
    ["心理機能", (config.functions || []).join("、")],
    ["history_mode", config.history_mode],
    ["使用した脳", [brain.provider, brain.model, brain.endpoint_kind].filter(Boolean).join(" / ")],
    ["実行環境", timing.machine_name],
    ["開始", timing.started_at],
    ["終了", timing.ended_at],
    ["所要時間", (timing.elapsed_seconds || 0) + "秒"],
    ["AI待機時間", (timing.ai_wait_seconds || 0) + "秒"],
    ["プロンプト版", ((log.players || [])[0] || {}).agent_prompt_version],
  ];
  return '<div class="scroll"><dl class="kv">' + items.map((item) =>
    "<dt>" + esc(item[0]) + "</dt><dd>" +
    esc(item[1] === undefined || item[1] === null || item[1] === "" ? "—" : item[1]) + "</dd>"
  ).join("") + "</dl></div>";
}

/* --- 過去の実行 ------------------------------------------------------- */

async function loadRuns() {
  try {
    const payload = await api("/api/runs?limit=100");
    const runs = payload.runs || [];
    runsHint.textContent = runs.length ? runs.length + "件" : "まだ実行はない。";
    runsList.innerHTML = runs.length ? renderRunsTable(runs) : "";
    Array.prototype.forEach.call(runsList.querySelectorAll("tr.clickable"), (row) => {
      row.addEventListener("click", () => showRun(row.dataset.runId));
    });
    highlightSelected();
  } catch (error) {
    runsHint.textContent = "一覧を読み込めなかった: " + String(error.message || error);
  }
}

function renderRunsTable(runs) {
  const body = runs.map((run) => "<tr class='clickable' data-run-id='" + esc(run.run_id) + "'>" + [
    run.run_id,
    STATUS_LABELS[run.status] || run.status,
    WINNER_LABELS[run.winner] || "—",
    run.executed || "—",
    run.provider || "—",
    run.elapsed_seconds === undefined || run.elapsed_seconds === null ? "—" : run.elapsed_seconds + "秒",
    run.started_at || "—",
    run.error_kind || "—",
  ].map((value) => "<td>" + esc(value) + "</td>").join("") + "</tr>").join("");
  return '<div class="scroll"><table><thead><tr><th>run_id</th><th>状態</th><th>勝敗</th>' +
    "<th>処刑</th><th>脳</th><th>所要</th><th>開始</th><th>失敗種別</th>" +
    "</tr></thead><tbody>" + body + "</tbody></table></div>";
}

function highlightSelected() {
  Array.prototype.forEach.call(runsList.querySelectorAll("tr"), (row) => {
    row.classList.toggle("selected", row.dataset.runId === selectedRunId);
  });
}

/* --- 起動 ------------------------------------------------------------- */

form.addEventListener("submit", startRun);
resetButton.addEventListener("click", () => {
  setFormEnabled(true);
  formHint.textContent = "";
});
document.getElementById("reload-runs").addEventListener("click", loadRuns);

(async function init() {
  try {
    fillForm(await api("/api/config/default"));
  } catch (error) {
    showError("既定の設定を読み込めなかった: " + String(error.message || error));
  }
  resetButton.disabled = true;
  setStatus(null, "", 0);
  await loadRuns();
})();
