# mbti-werewolf

MBTI16タイプの行動傾向を持つAIエージェント8体に「ワンナイト人狼」をさせ、性格傾向の差が
推理と議論に現れるかを観察するためのシミュレーター。

- 上位文書: [要求定義書](../../docs/requirements.md) / [要件定義書](../../docs/system-requirements.md) / [設計書](../../docs/design.md)
- ルールの正本: [`01_werewolf-rules_v0.7.md`](../../docs/m-plus-experiment/01_werewolf-rules_v0.7.md)
- プレイヤーは全員AI。人間は実行と観察だけを行う。
- 会話は実行完了後にまとめて表示する。1発言ずつ流すライブ表示は行わない。

MBTIおよび心理機能は、実在人物の診断や評価ではない。エージェントの振る舞いを分けるための
フィクション設定として扱っている。

---

## 1. セットアップ

Python 3.9以上が必要。macOSに最初から入っているPythonで動く。

```bash
cd playgrounds/mbti-werewolf
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

`pip install -e .` を実行すると、どのディレクトリからでも `python -m mbti_werewolf` が使える。
実行しない場合は、このディレクトリで `PYTHONPATH=src python -m mbti_werewolf ...` とする。

インストールする依存はすべて無料（OSSライセンス）で、認証情報も不要である。
確認記録は [docs/free-stack-check.md](../../docs/free-stack-check.md) にある。

---

## 2. 実験の単位

| 単位 | 中身 |
| --- | --- |
| ケース | 8人ワンナイト1試合。 |
| Trial | 17ケース。混合構成1ケースと、同質構成16ケース（16タイプそれぞれ全員同じ）。 |
| 実験 | 複数Trial。既定は1 Trial。 |

Trial内の17ケースは、人物・年齢・性別・役職・seedをすべて一致させ、MBTIだけを変える。
これが条件固定であり、比較の前提になる。

---

## 3. 実行する

```bash
python -m mbti_werewolf experiment                                   # 1 Trial（17ケース）
python -m mbti_werewolf experiment --dry-run                         # 生成と条件固定の検査だけ
python -m mbti_werewolf experiment --cases c00 --brain ollama            # 1ケースの実測（モデル省略時は gemma3:4b）
python -m mbti_werewolf experiment --trials 5 --brain ollama --model gemma3:4b
python -m mbti_werewolf experiment --trial-range 3-7                 # 分割実行
python -m mbti_werewolf experiment --resume e-20260901-210000        # 止まった実験を続ける
python -m mbti_werewolf judge --experiment e-20260901-210000         # 発言の事後評価
python -m mbti_werewolf analyze --experiment e-20260901-210000       # 分析出力（推論なし）
```

夜間の長時間実行はこの経路を使う。画面を開いたままにする必要がなく、`nohup` などで
シェルから切り離せる。

ケースを1件終えるごとにファイルへ書き出すため、途中で止めてもそこまでの結果は残る。
`--resume` は完了済みのケースを実行せず、条件を `trial.json` から復元してから続ける。

主なオプションは `--trials` `--trial-range` `--seed` `--cases` `--case-attempts`
`--max-rounds` `--brain` `--model` `--machine` `--config` `--data-dir` `--runs-dir`。
一覧は `python -m mbti_werewolf experiment --help` で確認できる。

操作画面（`ui` サブコマンド）は、v1の4人版と一緒にM3で削除した。M6でv2.0向けに作り直す。

---

## 3.1 発言を評価する（judge）

ゲームの実行が終わった後、発言を1件ずつ評価する。実行とは別のコマンドなので、
評価基準を変えてもゲームを回し直す必要がない。

```bash
python -m mbti_werewolf judge --experiment e-20260901-210000
python -m mbti_werewolf judge --experiment e-... --judge-brain ollama --judge-model gemma3:4b
python -m mbti_werewolf judge --experiment e-... --force      # 評価済みのケースもやり直す
```

評価は発言ごとに、9種のラベル（疑う・かばう・主張する など）、言及した相手、
公開スタンス（誰を・疑う/かばう・強さ1〜3）を付ける。結果はケースごとの
`judge.v1.json` に入る。既定では、まだ評価のないケースだけを見る。

Judgeには役職・MBTI・投票先・勝敗・非公開メモを渡さない。正解を知った評価に
すると「人狼の発言だから怪しい」という後付けになり、公開された会話から読み取れる
内容の評価にならないためである。

評価基準の文面は `src/mbti_werewolf/judge/criteria/v1/` にある。基準を変えるときは
`v2/` を作る。ファイル名に版が入るので、古い評価は消えない。

---

## 3.2 分析する（analyze）

`case_log.json` と `judge.v1.json` を読んで、人が読むレポートと集計CSVを作る。
推論は呼ばない。指標の定義を変えたら、このコマンドだけを回し直す。

```bash
python -m mbti_werewolf analyze --experiment e-20260901-210000
```

出力は実験ディレクトリに `experiment_report.md` / `experiment.html`、`rq1.md`、
`rq2.md`、`manipulation_check.md`、`speech_labels.csv` として残る。Trialごとには
`trial_report.md` がある。`latest.html` は実験の `experiment.html` へ向く。

JudgeがまだないTrialはRQ1・RQ2から除外し、除外理由をレポートに書く。
`final_entropy` と `convergence_round` は、Judgeがあるケースだけ埋まる。

---

## 4. エージェントの脳を切り替える

`--brain` または設定の `brain.provider` で切り替える。ゲーム進行側のコードは変わらない。

| provider | 通信先 | 用途 | 準備 |
| --- | --- | --- | --- |
| `stub` | なし | 進行・出力の確認、テスト。既定値。 | 不要 |
| `ollama` | `http://localhost:11434` | 本命。実際の議論を観察する。 | 下記 |
| `gemini` | Gemini API 無料枠 | 品質比較用。 | 環境変数 `GEMINI_API_KEY` |

`stub` はLLMを呼ばず、決まった形の応答を返す。議論としては無意味だが、待機時間ゼロで
1ケースが完走するため、出力形式の確認に使える。

Ollamaを使う場合の準備。`--model` を省略すると `gemma3:4b` になる。実行前に接続と
モデルの有無を確認し、無ければ警告を出す（実験は止めない）。1ケースが終わると
`timing.md` に所要時間が残る。

```bash
brew install ollama
ollama serve          # 別のターミナルで動かしておく
ollama pull gemma3:4b
python -m mbti_werewolf experiment --cases c00 --brain ollama
```

Geminiの無料枠は分間・1日の上限がある。上限に達した場合は自動で切り替えず、
`rate_limited` として失敗を記録する。長い実行はOllamaで行う。

---

## 5. マスタデータ

人物プールとMBTIパターンは `data/` に置く。生成し直すと過去の実験と条件が変わるため、
通常は生成済みのファイルをそのまま使う。

```text
data/
  rules/onenight-8p-v0.7.json      ルール文書v0.7の機械可読な写し
  persons/pool-001.json            人物プール（年齢・性別・MBTI）
  patterns/pattern-set-001.json    Trialごとに使う8人の組み合わせ
```

```bash
python -m mbti_werewolf masterdata --patterns 100
```

---

## 6. 出力

出力先はリポジトリの `runs/` 。`--runs-dir` または環境変数 `MBTI_WEREWOLF_RUNS_DIR`
で変更できる。

```text
runs/e-20260901-210000/
  experiment.json          実験全体の条件と進捗
  status.json              実験の進捗
  experiment_metrics.csv   1行 = 1ケース
  speech_labels.csv        1行 = 1発言（analyze 後）
  experiment_report.md
  experiment.html
  rq1.md / rq1.html
  rq2.md / rq2.html
  manipulation_check.md
  t001/
    trial.json             このTrialの固定条件（再開時に読む）
    status.json            Trialの進捗
    trial_report.md        17ケースを並べた補助分析
    trial.html
    trial_metrics.csv      1行 = 1ケース1プレイヤー
    c00-mixed/
      config.json          このケースの確定した実験条件
      status.json          進捗
      case_log.json        出力の正本。他のファイルはここから導出する
      transcript.md        会話全文とprivate memo（先行実験のWORLD A / B形式）
      summary.md           結果の要約（会話は載せない）
      result.html          自己完結の結果ビュー
      judge.v1.json        発言の評価（judge コマンドを実行すると増える）
    c01-ISTJ/ ... c16-ENTJ/
runs/latest.html           分析後は実験の experiment.html へ転送（実行中は直近ケース）
```

`result.html` は外部と通信しない1ファイルで、スマホのブラウザでもそのまま読める。
Pythonを動かせないメンバーはこれを開く。GitHub Pages の一覧は
https://ziriss8120121.github.io/hackathon-test/ から同じファイルを開く。

```bash
python -m mbti_werewolf pages --out site
```

生成物は `gh-pages` ブランチへ載せて公開する。

集計CSVの `final_entropy` と `convergence_round` は、`analyze` を回すまで空欄になる。
Judgeがない状態で分析すると、そのTrialはRQから除外される。分母が0になる割合も
空欄にする。0と区別するためである。

---

## 7. テスト

```bash
python -m pytest
```

すべて `stub` と差し替え用の脳で動く。LLMを呼ばないので、無料枠もモデルの
ダウンロードも消費しない。

| ファイル | 確認していること |
| --- | --- |
| `test_rules.py` | ルールJSONの読み込みと検証 |
| `test_experiment.py` | 人物選定、役職割当、Trialと17ケースの生成 |
| `test_condition_fixation.py` | 17ケースでMBTI以外の条件が一致する |
| `test_night.py` | 開始時の役職処理と最終役職 |
| `test_discussion.py` | 自由議論のラウンド制御と終了条件 |
| `test_private_answers.py` | 2時点の個別判断とprivate memo |
| `test_vote.py` | 投票の収集と同数得票の扱い |
| `test_execution.py` | 追放と勝敗判定 |
| `test_isolation.py` | 他者の役職、MBTI、他者の個別判断が渡らない |
| `test_brain_parse.py` | 形式が崩れた応答の再送と3回失敗の扱い |
| `test_resume.py` | 中断と再開、失敗ケースの再実行 |
| `test_transcript.py` | `transcript.md` が先行実験の形式に沿う |
| `test_case_metrics.py` | 指標の算出と、算出できない場合の扱い |
| `test_case_outputs.py` | `summary.md`・`result.html`・集計CSVの形 |
| `test_run_outputs.py` | 実行を通して出力ファイルが揃う |
| `test_judge.py` | 発言と評価が1対1に対応し、Judgeへ正解が渡らない |
| `test_stance.py` | 疑念分布が発言量に引きずられない |
| `test_analysis.py` | 不完全Trialの除外、Judge列の充填、RQ1/RQ2の注記 |
| `test_cli.py` | コマンド起動と各サブコマンド |
| `test_ollama.py` | Ollamaの失敗分類。実モデルは呼ばない |

---

## 8. コードの構成

依存は外から内へ一方向。`engine` と `agents` は脳の具体実装をimportしない。
推論手段を追加するときに触るのは `brains/` と設定の選択肢だけである。

```text
src/mbti_werewolf/
  __main__.py     experiment / judge / analyze / masterdata / pages のサブコマンド
  config.py       実験条件の読み込みと検証
  experiment.py   人物選定、役職割当、Trialと17ケースの生成、条件固定の検査
  runner.py       実行管理、逐次保存、再開
  masterdata.py   人物プールとパターンセットの生成
  engine/         ゲーム進行（rules / case / roles / night / discussion / vote / view）
  agents/         プロンプト組み立てと応答の解釈（agent / persona / mbti_types / functions）
  brains/         推論手段（base / stub / ollama / gemini / factory）
  record/         出力の生成（case_log / transcript / summary / case_metrics / metrics_csv / result_view / pages / timing）
  judge/          発言の事後評価（judge / stance / criteria）
  analysis/       指標・検定・レポート（indicators / stats / analyzer）
```
