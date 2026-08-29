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
python -m mbti_werewolf experiment --cases c00 --brain ollama --model gemma3:4b   # 1ケースの実測
python -m mbti_werewolf experiment --trials 5 --brain ollama --model gemma3:4b
python -m mbti_werewolf experiment --trial-range 3-7                 # 分割実行
python -m mbti_werewolf experiment --resume e-20260901-210000        # 止まった実験を続ける
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

## 4. エージェントの脳を切り替える

`--brain` または設定の `brain.provider` で切り替える。ゲーム進行側のコードは変わらない。

| provider | 通信先 | 用途 | 準備 |
| --- | --- | --- | --- |
| `stub` | なし | 進行・出力の確認、テスト。既定値。 | 不要 |
| `ollama` | `http://localhost:11434` | 本命。実際の議論を観察する。 | 下記 |
| `gemini` | Gemini API 無料枠 | 品質比較用。 | 環境変数 `GEMINI_API_KEY` |

`stub` はLLMを呼ばず、決まった形の応答を返す。議論としては無意味だが、待機時間ゼロで
1ケースが完走するため、出力形式の確認に使える。

Ollamaを使う場合の準備。

```bash
brew install ollama
ollama serve          # 別のターミナルで動かしておく
ollama pull gemma3:4b
python -m mbti_werewolf experiment --cases c00 --brain ollama --model gemma3:4b
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
  t001/
    trial.json             このTrialの固定条件（再開時に読む）
    status.json            Trialの進捗
    trial_metrics.csv      1行 = 1ケース1プレイヤー
    c00-mixed/
      config.json          このケースの確定した実験条件
      status.json          進捗
      case_log.json        出力の正本。他のファイルはここから導出する
      transcript.md        会話全文とprivate memo（先行実験のWORLD A / B形式）
      summary.md           結果の要約（会話は載せない）
      result.html          自己完結の結果ビュー
    c01-ISTJ/ ... c16-ENTJ/
runs/latest.html           直近に完了したケースの result.html への転送
```

`result.html` は外部と通信しない1ファイルで、スマホのブラウザでもそのまま読める。
Pythonを動かせないメンバーはこれを開く。GitHub Pages の一覧は
https://ziriss8120121.github.io/hackathon-test/ から同じファイルを開く。

```bash
python -m mbti_werewolf pages --out site
```

生成物は `gh-pages` ブランチへ載せて公開する。

集計CSVは、Judgeの出力に依存する2列（`final_entropy` と `convergence_round`）が
M4まで空欄になる。分母が0になる割合も空欄にする。0と区別するためである。

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
| `test_cli.py` | コマンド起動と各サブコマンド |

---

## 8. コードの構成

依存は外から内へ一方向。`engine` と `agents` は脳の具体実装をimportしない。
推論手段を追加するときに触るのは `brains/` と設定の選択肢だけである。

```text
src/mbti_werewolf/
  __main__.py     experiment / masterdata / pages のサブコマンド
  config.py       実験条件の読み込みと検証
  experiment.py   人物選定、役職割当、Trialと17ケースの生成、条件固定の検査
  runner.py       実行管理、逐次保存、再開
  masterdata.py   人物プールとパターンセットの生成
  engine/         ゲーム進行（rules / case / roles / night / discussion / vote / view）
  agents/         プロンプト組み立てと応答の解釈（agent / persona / mbti_types / functions）
  brains/         推論手段（base / stub / ollama / gemini / factory）
  record/         出力の生成（case_log / transcript / summary / case_metrics / metrics_csv / result_view / pages）
```

M4以降で `judge/` と `analysis/` を追加する。
