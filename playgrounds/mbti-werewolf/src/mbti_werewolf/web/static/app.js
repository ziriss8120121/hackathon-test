/* 操作画面。状態の正本は runs/ で、画面は API を読むだけ（設計書7.1）。 */
(function () {
  var app = document.getElementById("app");
  var pollTimer = null;
  var POLL_EXPERIMENT_MS = 5000;
  var POLL_CASE_MS = 2000;

  function api(path, options) {
    return fetch(path, options).then(function (res) {
      return res.json().then(function (body) {
        if (!res.ok) {
          var err = new Error(body.detail || res.statusText || "エラー");
          err.status = res.status;
          err.body = body;
          throw err;
        }
        return { status: res.status, body: body };
      });
    });
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function statusClass(status) {
    if (status === "running") return "status-running";
    if (status === "done" || status === true) return "status-done";
    if (status === "failed") return "status-failed";
    return "";
  }

  function statusLabel(status) {
    var map = {
      running: "実行中",
      done: "完了",
      failed: "失敗",
      pending: "未実行",
      skipped: "実行せず",
      missing: "未生成",
      ready: "あり",
    };
    return map[status] || status || "—";
  }

  function parseHash() {
    var raw = (location.hash || "#/run").replace(/^#/, "");
    var parts = raw.split("/").filter(Boolean);
    return { view: parts[0] || "run", id: parts.slice(1).join("/") };
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function startPoll(ms, fn) {
    stopPoll();
    pollTimer = setInterval(fn, ms);
  }

  function optionList(items, idKey, selected) {
    return items
      .map(function (item) {
        var id = item[idKey];
        return (
          '<option value="' +
          esc(id) +
          '"' +
          (id === selected ? " selected" : "") +
          ">" +
          esc(id) +
          "</option>"
        );
      })
      .join("");
  }

  function renderRun() {
    Promise.all([
      api("/api/config/default"),
      api("/api/data/pools"),
      api("/api/data/patterns"),
      api("/api/data/rules"),
    ])
      .then(function (results) {
        var config = results[0].body;
        var discussion = config.discussion || {};
        var brain = config.brain || {};
        app.innerHTML =
          "<h1>実験を実行する</h1>" +
          '<p class="sub">条件を選んで開始します。長い実行はコマンドの方が安全です。</p>' +
          '<form id="run-form" class="panel">' +
          '<div class="grid">' +
          "<label>人物プール<select name=\"pool_id\">" +
          optionList(results[1].body, "pool_id", config.pool_id) +
          "</select></label>" +
          "<label>パターンセット<select name=\"pattern_set_id\">" +
          optionList(results[2].body, "pattern_set_id", config.pattern_set_id) +
          "</select></label>" +
          "<label>ルールセット<select name=\"rule_set_id\">" +
          optionList(results[3].body, "rule_set_id", config.rule_set_id) +
          "</select></label>" +
          '<label>Trial数<input name="trial_count" type="number" min="1" value="' +
          esc(config.trial_count) +
          '"></label>' +
          '<label>Trial範囲（例 3-7）<input name="trial_range" placeholder="空なら全部"></label>' +
          '<label>seed<input name="base_seed" type="number" value="' +
          esc(config.base_seed) +
          '"></label>' +
          '<label>max_rounds<input name="max_rounds" type="number" min="1" value="' +
          esc(discussion.max_rounds) +
          '"></label>' +
          '<label>max_speeches<input name="max_speeches" type="number" min="1" value="' +
          esc(discussion.max_speeches) +
          '"></label>' +
          '<label>max_speech_chars<input name="max_speech_chars" type="number" min="1" value="' +
          esc(discussion.max_speech_chars) +
          '"></label>' +
          "<label>脳<select name=\"brain_provider\">" +
          ["stub", "ollama", "gemini"]
            .map(function (p) {
              return (
                '<option value="' +
                p +
                '"' +
                (brain.provider === p ? " selected" : "") +
                ">" +
                p +
                "</option>"
              );
            })
            .join("") +
          "</select></label>" +
          '<label>モデル<input name="brain_model" value="' +
          esc(brain.model) +
          '" placeholder="省略可"></label>' +
          '<label>人格プロンプト版<input name="persona_prompt_version" value="' +
          esc(config.persona_prompt_version) +
          '"></label>' +
          '<label>Judge基準版<input name="judge_criteria_version" value="' +
          esc(config.judge_criteria_version) +
          '"></label>' +
          '<label>ケース絞り込み<input name="cases" placeholder="例: c00"></label>' +
          "</div>" +
          '<div class="actions"><button type="submit">実行する</button></div>' +
          '<p class="error" id="run-error"></p>' +
          "</form>";

        document.getElementById("run-form").addEventListener("submit", function (event) {
          event.preventDefault();
          var form = event.target;
          var errorEl = document.getElementById("run-error");
          errorEl.textContent = "";
          var body = {
            pool_id: form.pool_id.value,
            pattern_set_id: form.pattern_set_id.value,
            rule_set_id: form.rule_set_id.value,
            trial_count: Number(form.trial_count.value),
            base_seed: Number(form.base_seed.value),
            persona_prompt_version: form.persona_prompt_version.value,
            judge_criteria_version: form.judge_criteria_version.value,
            discussion: {
              max_rounds: Number(form.max_rounds.value),
              max_speeches: Number(form.max_speeches.value),
              max_speech_chars: Number(form.max_speech_chars.value),
            },
            brain: {
              provider: form.brain_provider.value,
              model: form.brain_model.value || undefined,
            },
          };
          if (form.trial_range.value.trim()) {
            var parts = form.trial_range.value.replace("〜", "-").split("-");
            body.trial_range = [Number(parts[0]), Number(parts[1])];
          }
          if (form.cases.value.trim()) body.cases = form.cases.value.trim();
          form.querySelector("button").disabled = true;
          api("/api/experiments", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          })
            .then(function (result) {
              location.hash = "#/experiments/" + result.body.experiment_id;
            })
            .catch(function (err) {
              errorEl.textContent = err.message;
              form.querySelector("button").disabled = false;
            });
        });
      })
      .catch(function (err) {
        app.innerHTML = '<p class="error">' + esc(err.message) + "</p>";
      });
  }

  function renderExperiments() {
    api("/api/experiments")
      .then(function (result) {
        var items = result.body;
        var cards = items.length
          ? items
              .map(function (item) {
                return (
                  '<a class="card" href="#/experiments/' +
                  encodeURIComponent(item.experiment_id) +
                  '"><strong>' +
                  esc(item.experiment_id) +
                  '</strong><div class="' +
                  statusClass(item.status) +
                  '">' +
                  esc(statusLabel(item.status)) +
                  "</div><div class=\"muted\">Trial " +
                  esc(item.trial_complete) +
                  " / " +
                  esc(item.trial_total) +
                  "　ケース " +
                  esc(item.case_done) +
                  " / " +
                  esc(item.case_total) +
                  "</div></a>"
                );
              })
              .join("")
          : '<p class="muted">まだ実験がありません。</p>';
        app.innerHTML = "<h1>実験一覧</h1>" + '<div class="cards">' + cards + "</div>";
      })
      .catch(function (err) {
        app.innerHTML = '<p class="error">' + esc(err.message) + "</p>";
      });
  }

  function renderExperiment(id) {
    function load() {
      return Promise.all([
        api("/api/experiments/" + encodeURIComponent(id)),
        api("/api/experiments/" + encodeURIComponent(id) + "/trials"),
        api("/api/experiments/" + encodeURIComponent(id) + "/analysis/experiment"),
        api("/api/experiments/" + encodeURIComponent(id) + "/analysis/rq1"),
        api("/api/experiments/" + encodeURIComponent(id) + "/analysis/rq2"),
      ]).then(function (results) {
        var exp = results[0].body;
        var trials = results[1].body;
        var analysis = results[2].body;
        var rq1 = results[3].body;
        var rq2 = results[4].body;
        var rows = trials
          .map(function (trial) {
            return (
              "<tr><td><a href=\"#/trials/" +
              encodeURIComponent(trial.trial_id) +
              '">' +
              esc(trial.trial_id) +
              "</a></td><td class=\"" +
              statusClass(trial.status) +
              '">' +
              esc(statusLabel(trial.status)) +
              "</td><td>" +
              esc(trial.case_done) +
              " / " +
              esc(trial.case_total) +
              "</td><td>" +
              (trial.complete ? "揃っている" : "不完全") +
              "</td></tr>"
            );
          })
          .join("");
        app.innerHTML =
          "<h1>" +
          esc(id) +
          "</h1>" +
          '<p class="' +
          statusClass(exp.status) +
          '">' +
          esc(statusLabel(exp.status)) +
          (exp.current_case_id ? "　いま " + esc(exp.current_case_id) : "") +
          "</p>" +
          '<div class="actions">' +
          '<button type="button" id="resume-btn" class="secondary">再開する</button>' +
          '<a class="btn secondary" href="#/experiments">一覧へ</a>' +
          "</div>" +
          "<h2>Trial</h2>" +
          '<div class="panel"><table><thead><tr><th>ID</th><th>状態</th><th>ケース</th><th>比較</th></tr></thead><tbody>' +
          rows +
          "</tbody></table></div>" +
          "<h2>分析</h2>" +
          '<div class="panel"><p>全体: ' +
          esc(statusLabel(analysis.status)) +
          "　有効Trial " +
          esc(analysis.eligible_count) +
          "　除外 " +
          esc(analysis.excluded_count) +
          "</p><p>RQ1: " +
          esc(statusLabel(rq1.status)) +
          "　<a href=\"/runs/" +
          encodeURIComponent(id) +
          '/rq1.html">開く</a>　RQ2: ' +
          esc(statusLabel(rq2.status)) +
          "　<a href=\"/runs/" +
          encodeURIComponent(id) +
          '/rq2.html">開く</a></p>' +
          (analysis.status === "ready"
            ? '<p><a href="/runs/' + encodeURIComponent(id) + '/experiment.html">全体分析HTML</a></p>'
            : "<p class=\"muted\">分析は python -m mbti_werewolf analyze で作ります。</p>") +
          "</div>";
        document.getElementById("resume-btn").onclick = function () {
          api("/api/experiments/" + encodeURIComponent(id) + "/resume", { method: "POST" })
            .then(load)
            .catch(function (err) {
              alert(err.message);
            });
        };
        if (exp.status === "running") startPoll(POLL_EXPERIMENT_MS, load);
        else stopPoll();
      });
    }
    load().catch(function (err) {
      app.innerHTML = '<p class="error">' + esc(err.message) + "</p>";
    });
  }

  function renderTrial(id) {
    api("/api/trials/" + encodeURIComponent(id))
      .then(function (result) {
        var trial = result.body;
        var fixed = trial.fixed_conditions || {};
        var rows = (trial.cases || [])
          .map(function (caseRow) {
            return (
              "<tr><td><a href=\"#/cases/" +
              encodeURIComponent(caseRow.case_id) +
              '">' +
              esc(caseRow.case_id) +
              "</a></td><td>" +
              esc(caseRow.composition) +
              "</td><td>" +
              esc(caseRow.homogeneous_type || "混合") +
              '</td><td class="' +
              statusClass(caseRow.status) +
              '">' +
              esc(statusLabel(caseRow.status)) +
              "</td></tr>"
            );
          })
          .join("");
        app.innerHTML =
          "<h1>" +
          esc(id) +
          "</h1>" +
          '<p class="sub"><a href="#/experiments/' +
          encodeURIComponent(trial.experiment_id) +
          '">実験へ戻る</a></p>' +
          "<h2>固定条件</h2>" +
          '<dl class="kv panel"><dt>seed</dt><dd>' +
          esc(trial.trial_seed) +
          "</dd><dt>パターン</dt><dd>" +
          esc(trial.pattern_id) +
          "</dd><dt>ルール</dt><dd>" +
          esc(trial.rule_set_id) +
          "</dd><dt>脳</dt><dd>" +
          esc((fixed.brain || {}).provider) +
          " / " +
          esc((fixed.brain || {}).model) +
          "</dd></dl>" +
          "<h2>17ケース</h2>" +
          '<div class="panel"><table><thead><tr><th>ケース</th><th>構成</th><th>タイプ</th><th>状態</th></tr></thead><tbody>' +
          rows +
          "</tbody></table></div>";
      })
      .catch(function (err) {
        app.innerHTML = '<p class="error">' + esc(err.message) + "</p>";
      });
  }

  function renderCase(id) {
    function load() {
      return Promise.all([
        api("/api/cases/" + encodeURIComponent(id)),
        api("/api/cases/" + encodeURIComponent(id) + "/log").catch(function () {
          return { body: null };
        }),
        api("/api/cases/" + encodeURIComponent(id) + "/judge"),
      ]).then(function (results) {
        var status = results[0].body;
        var log = results[1].body;
        var judge = results[2].body;
        var result = (log && log.result) || {};
        var failure = status.error || (log && log.failure);
        app.innerHTML =
          "<h1>" +
          esc(id) +
          "</h1>" +
          '<p class="' +
          statusClass(status.status) +
          '">' +
          esc(statusLabel(status.status)) +
          "</p>" +
          (failure
            ? '<div class="panel error">失敗: ' +
              esc((failure.kind || "") + " " + (failure.message || JSON.stringify(failure))) +
              "</div>"
            : "") +
          '<dl class="kv panel"><dt>勝敗</dt><dd>' +
          esc(result.valid === false ? "無効試合" : result.winner || "—") +
          "</dd><dt>Judge</dt><dd>" +
          esc(statusLabel(judge.status)) +
          "</dd></dl>" +
          (status.result_href
            ? '<p><a href="' +
              esc(status.result_href) +
              '">結果HTMLを開く</a></p><iframe class="result" src="' +
              esc(status.result_href) +
              '"></iframe>'
            : "<p class=\"muted\">結果HTMLはまだありません。</p>");
        if (status.status === "running") startPoll(POLL_CASE_MS, load);
        else stopPoll();
      });
    }
    load().catch(function (err) {
      app.innerHTML = '<p class="error">' + esc(err.message) + "</p>";
    });
  }

  function route() {
    stopPoll();
    var parsed = parseHash();
    if (parsed.view === "experiments" && parsed.id) renderExperiment(parsed.id);
    else if (parsed.view === "experiments") renderExperiments();
    else if (parsed.view === "trials" && parsed.id) renderTrial(parsed.id);
    else if (parsed.view === "cases" && parsed.id) renderCase(parsed.id);
    else renderRun();
  }

  window.addEventListener("hashchange", route);
  route();
})();
