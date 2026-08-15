# mbti-werewolf

心理機能（MBTI風の行動ルール）を持つAIエージェント同士に人狼をさせ、行動ルールの差が
ログに現れるかを観察するためのシミュレーター。

- 上位文書: [要求定義書](../../docs/requirements.md) / [要件定義書](../../docs/system-requirements.md) / [設計書](../../docs/design.md)
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

## 2. 実行する

### 操作画面から

```bash
python -m mbti_werewolf ui
```

`http://127.0.0.1:8765/` が開く。条件を設定して「対戦開始」を押すと実行が始まり、
完了後に同じ画面で会話タイムラインと結果が表示される。停止は Ctrl+C。

### コマンドから

```bash
python -m mbti_werewolf run                        # 1試合
python -m mbti_werewolf run --games 100 --seed 42  # 100試合
python -m mbti_werewolf run --brain ollama --model gemma3:4b
python -m mbti_werewolf run --players 8 --werewolves 2 --functions Ne,Ti,Fe,Si,Ni,Se,Te,Fi
```

夜間の長時間実行はこちらを使う。画面を開いたままにする必要がなく、`nohup` などで
シェルから切り離せる。

主なオプションは `--games` `--seed` `--players` `--turns` `--werewolves` `--functions`
`--brain` `--model` `--max-output-chars` `--config` `--runs-dir`。
一覧は `python -m mbti_werewolf run --help` で確認できる。

---

## 3. エージェントの脳を切り替える

`--brain` または設定の `brain.provider` で切り替える。ゲーム進行側のコードは変わらない。

| provider | 通信先 | 用途 | 準備 |
| --- | --- | --- | --- |
| `stub` | なし | 進行・出力・画面の確認、テスト。既定値。 | 不要 |
| `ollama` | `http://localhost:11434` | 本命。実際の議論を観察する。 | 下記 |
| `gemini` | Gemini API 無料枠 | 品質比較用。 | 環境変数 `GEMINI_API_KEY` |

`stub` はLLMを呼ばず、心理機能ごとの固定文を返す。議論としては無意味だが、
待機時間ゼロで1試合が完走するため、出力形式と画面の確認に使える。

Ollamaを使う場合の準備。

```bash
brew install ollama
ollama serve          # 別のターミナルで動かしておく
ollama pull gemma3:4b
python -m mbti_werewolf run --brain ollama --model gemma3:4b
```

1試合あたりの推論回数は 発言12回 + 投票4回 = 16回。Geminiの既定モデルは
`gemini-3.1-flash-lite`。無料枠は分間・1日の上限があるため、100試合以上はOllamaで行う。
上限に達した場合は自動で切り替えず、`rate_limited` として失敗を記録する。

---

## 4. 出力

出力先はリポジトリの `runs/` 。`--runs-dir` または環境変数 `MBTI_WEREWOLF_RUNS_DIR`
で変更できる。1試合だけの実行も1試合のseriesとして扱う。

```text
runs/s-20260815-190959/
  series.json          実行全体の状態と試合ごとの結果
  series_summary.md    試合数、勝率、心理機能別の集計
  r001/
    config.json        この試合の確定した実験条件
    status.json        進捗（画面が1秒ごとに読む）
    run_log.json       出力の正本。他のファイルはここから導出する
    summary.md         結果カード
    timeline.md        会話タイムライン
    metrics.csv        1行 = 1プレイヤーの集計
    result.html        自己完結の結果ビュー
```

`result.html` は結果データを埋め込んだ1ファイルで、外部と通信しない。
Pythonを動かせないメンバーはこれをブラウザで開けばよい。

`metrics.csv` は複数試合分を縦に連結すれば、そのまま表計算ソフトで機能別に集計できる。

---

## 5. テスト

```bash
python -m pytest
```

すべて `stub` と差し替え用の脳で動く。LLMを呼ばないので、無料枠もモデルの
ダウンロードも消費しない。

| ファイル | 確認していること |
| --- | --- |
| `test_engine.py` | 1試合の完走と出力ファイルの生成 |
| `test_reproducibility.py` | 同じseedで割当と進行順序が再現される |
| `test_role_isolation.py` | 村人視点のプロンプトに他者の役職が出ない |
| `test_brain_parse.py` | 形式が崩れた応答でも試合が完走し、事象が残る |
| `test_tiebreak.py` | 同数得票でも試合が終了し、決着方法が残る |
| `test_failure_record.py` | 失敗時に原因の種別と部分結果が残る |
| `test_web_api.py` | 画面から実行するAPIの契約 |
| `test_cli.py` | コマンド起動と、設定だけでの条件変更 |

---

## 6. コードの構成

依存は外から内へ一方向。`engine` と `agents` は脳の具体実装をimportしない。
推論手段を追加するときに触るのは `brains/` と設定の選択肢だけである。

```text
src/mbti_werewolf/
  __main__.py     ui / run のサブコマンド
  config.py       設定の読み込みと検証
  runner.py       実行管理、進捗と出力の書き込み
  engine/         ゲーム進行（game / roles / view / tiebreak）
  agents/         プロンプト組み立てと応答の解釈、心理機能の行動ルール
  brains/         推論手段（base / stub / ollama / gemini / factory）
  record/         出力の生成（run_log / metrics / summary / timeline / series / result_view）
  web/            FastAPIと操作画面の静的ファイル
```

画面の見た目を変えるときに触るのは `web/static/` の3ファイルだけで、実行側には
手を入れない。ビルド工程は持たない。
