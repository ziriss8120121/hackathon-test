# 無料構成の確認記録

要件のNF-01、NF-02、AC-07（課金を伴う認証情報を用いずに1ゲームを完走できること）を
満たしていると判断した根拠を残す。設計書1.3の確認手順に対応する。

| 項目 | 内容 |
| --- | --- |
| 確認日 | 2026-08-15 |
| 確認者 | ゆうじろう（Engineer） |
| 確認した実機 | MacBook Air（Apple Silicon） |

---

## 1. 実行環境

| 項目 | 実測値 | 備考 |
| --- | --- | --- |
| Python | 3.9.6 | macOSのCommandLineToolsに同梱。追加インストールなし。 |
| パッケージ管理 | `venv` + `pip` | Python同梱。Homebrewもpyenvも不要。 |
| Ollama | 0.32.13 | Homebrewなし。公式darwin tarballを `~/.local/ollama/` に展開し、`~/.local/bin/ollama` から起動。 |
| 推論デバイス | Apple M2（Metal、VRAM 11.8 GiB） | `ollama serve` が自動検出。 |

設計書1.1では「Python 3.12以上」としていたが、確認した実機には3.9.6しか入っていなかった。
新しいPythonを入れる作業自体が導入の障壁になる（要件NF-04）ため、実装を3.9で動く書き方に
そろえた。3.12でもそのまま動く。

## 2. 依存パッケージのライセンスと料金区分

`playgrounds/mbti-werewolf/requirements.txt` に固定したもの。すべてOSSで、利用に
課金は発生しない。

| パッケージ | バージョン | ライセンス | 料金 | 必要になる場面 |
| --- | --- | --- | --- | --- |
| fastapi | 0.128.8 | MIT | 無料 | 操作画面（`ui` サブコマンド） |
| uvicorn | 0.39.0 | BSD-3-Clause | 無料 | 操作画面 |
| httpx | 0.28.1 | BSD-3-Clause | 無料 | Ollama / Gemini への通信 |
| pytest | 8.4.2 | MIT | 無料 | テスト |

間接依存（starlette、pydantic、anyio、click、h11、httpcore、certifi、idna、
typing-extensions、annotated-types、sniffio、pluggy、iniconfig、packaging、
pygments、exceptiongroup、tomli）もすべてMITまたはBSD系のOSSである。

`stub` で実行する場合は標準ライブラリだけで動く。CLIから1試合を回すだけなら
追加インストールも不要である。

## 3. 課金経路がないことの確認

| 確認 | 結果 |
| --- | --- |
| APIキーを設定しない状態で1試合が完走するか | 完走する。`python -m mbti_werewolf run --brain stub` および `--brain ollama`（ローカル）はどちらも認証情報を要求しない。 |
| 環境変数 `GEMINI_API_KEY` が未設定のときの挙動 | `gemini` を選んだ場合のみ `unreachable` として失敗する。既定は `stub` なので、未設定でも実行に支障はない。 |
| 出力物に認証情報が含まれないか | 含まれない。APIキーは環境変数からのみ読み、`config.json` にも `run_log.json` にも書き出さない（要件NF-11）。 |
| Geminiの課金 | 有効化しない。有効化すると無料枠を外れるため、有効化しないこと自体を運用ルールとする。 |

## 4. モデルの重み

| 項目 | 状況 |
| --- | --- |
| 確認日 | 2026-08-15 |
| 既定モデル | `gemma3:4b`（Ollama経由、digest `a2af6cc3eb7f`） |
| 取得方法 | `ollama pull gemma3:4b`。重みは `~/.ollama/models` に保存。リポジトリには含めない。 |
| 実測サイズ | 3.3 GB（Ollama表示。GGUF、family=`gemma3`、4.3B、量子化 `Q4_K_M`） |
| 利用規約 | [Gemma Terms of Use](https://ai.google.dev/gemma/terms)（最終更新 2026-04-01）。Gemma 3 は Appendix に含まれる。 |
| 禁止用途 | [Gemma Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy) が規約 3.2 で組み込まれる。 |
| 料金 | ローカル実行は回数制限なし。APIキーも課金も不要。 |
| OSIオープンソースか | ではない。利用・複製・改変・配布は規約に従う範囲で認められる。Gemma 4 は Apache 2.0 だが、本プロジェクトが使うのは Gemma 3。 |
| 生成物 | Google は Output に権利を主張しない（規約 3.3）。利用責任は利用者側。 |
| この用途での判断 | フィクションの心理機能と人狼議論であり、実在人物の診断・評価ではない。禁止用途に当たらないと判断した。 |

Ollama本体のライセンスは MIT。モデルの重みは Ollama 本体とは別契約である。
この節をもって、無料であることの確認は依存パッケージ・API・モデルの重みまで完了した。

## 5. 出力容量の実測（要件NF-10）

`stub` で4人・3ターン・1試合を実行したときの1試合あたりの出力。

| ファイル | サイズ |
| --- | --- |
| `result.html` | 約17KB |
| `run_log.json` | 約8.8KB |
| `timeline.md` | 約2.8KB |
| `summary.md` | 約1.9KB |
| `config.json` | 約0.5KB |
| `metrics.csv` | 約0.6KB |
| `status.json` | 約0.3KB |
| 合計 | **約32KB** |

100試合で約3.2MB。実際のLLMを使うと発言が長くなるため増えるが、桁は変わらない。
リポジトリ運用を破綻させる水準ではないため、当面は出力をそのままcommitする方針で進める。

同じ条件（4人・3ターン・1試合、seed=42）を `ollama` / `gemma3:4b` で回したときの1試合あたり。

| ファイル | サイズ |
| --- | --- |
| `result.html` | 約19.6KB |
| `run_log.json` | 約11.4KB |
| `timeline.md` | 約5.4KB |
| `summary.md` | 約1.9KB |
| `config.json` | 約0.5KB |
| `metrics.csv` | 約0.6KB |
| `status.json` | 約0.3KB |
| 合計 | **約40KB** |

stubの約32KBから約1.3倍。100試合でも約4MBであり、桁は変わらない。

## 6. 実測した所要時間（要件NF-06）

実行: `python -m mbti_werewolf run --brain ollama --model gemma3:4b --seed 42`
保存先: `runs/s-20260815-194748/`

| 項目 | 実測値 |
| --- | --- |
| 条件 | 4人 / 3ターン / 1試合 / 推論16回（発言12 + 投票4） |
| 所要時間 | 169.827秒（約2分50秒） |
| AI待機時間 | 169.807秒（所要時間のほぼ全部） |
| 勝敗 | 人狼陣営の勝ち（処刑 p4、人狼は Fe / p3） |
| parse_failed | 0 |
| 乱数フォールバック投票 | 0 |
| 議論 | stubの定型文ではなく、参加者同士の言及がある自然文 |

当面の目安は **1試合10分以内** とする。今回は約2分50秒で満たした。
100試合換算は約4.7時間で、夜間実行で成立する。進行処理自体は無視できる厚さであり、
待ち時間は推論側が支配する。

## 7. 操作画面の経路確認

確認日: 2026-08-15。`python -m mbti_werewolf ui --host 127.0.0.1 --port 8765` を起動し、
画面（`index.html` / `app.js`）が使う HTTP 経路を同じ順で叩いた。

| 画面上の操作 | 確認した経路 | 結果 |
| --- | --- | --- |
| 画面を開く | `GET /`、`GET /static/app.js`、`GET /static/style.css` | 200。フォーム、対戦開始、免責文あり |
| 条件の初期表示 | `GET /api/config/default` | 既定は stub / 4人 |
| 過去の実行一覧 | `GET /api/runs?limit=100` | Ollama試合 `s-20260815-194748-r001` を含む |
| 過去結果の復元 | `GET /api/runs/{id}`、`/log`、`GET /api/series/{id}`、`GET /runs/.../result.html` | Ollama試合を画面経由で読める |
| 対戦開始 | `POST /api/runs`（stub・1試合・seed=7） | 202 queued → ポーリングで done |
| 連続実行 | `POST /api/runs`（stub・3試合） | 成功 3 / 失敗 0 |
| 実行中の再開始 | 3試合中に再度 POST | 409 |
| 不正な人数 | `player_count: 2` | 400（3以上） |

UI経由のstub実行は `runs/s-20260815-195432/`（1試合）と `runs/s-20260815-195432-2/`（3試合）。

実ブラウザでの見た目・クリックは未実施（Designer確認）。

## 8. Gemini無料枠での1試合（2026-08-15）

実行: `python -m mbti_werewolf run --brain gemini --model gemini-3.1-flash-lite --seed 42`
保存先: `runs/s-20260815-212647/`
APIキーは環境変数（`.env`、gitignore済み）からのみ読み、出力には含まれない。

| 項目 | 実測値 |
| --- | --- |
| モデル | `gemini-3.1-flash-lite`（既定の `gemini-2.5-flash-lite` は新規ユーザーに 404） |
| 条件 | 4人 / 3ターン / 1試合 / 推論16回 |
| 所要時間 | 129.594秒（約2分10秒） |
| AI待機時間 | 129.578秒 |
| 勝敗 | 人狼陣営の勝ち（処刑 p1、人狼は Fe / p3） |
| parse_failed | 0 |
| 乱数フォールバック投票 | 0 |
| 出力容量 | 約50KB（timeline 約8.8KB。Ollamaより発言が長い） |
| 課金 | 無料枠のまま。お支払い情報は未設定 |

間隔を空けずに連続呼び出しすると、投票途中で `rate_limited`（429）になる。
`GeminiBrain` は呼び出し間隔 7秒を空ける。100試合は無料枠では成立しない。

失敗経路も確認した。キー未設定は `unreachable`（`runs/s-20260815-210707/`）。
廃止モデルは `invalid_response` / 404（`runs/s-20260815-212321/`）。

## 9. 未確認のまま残っている項目

| 項目 | 理由 | 決める時期 |
| --- | --- | --- |
| Gemini無料枠の1日あたり上限 | 分間の 429 は観測した。1日あたりの回数は AI Studio の使用量画面で未確認。 | 多試合を Gemini で回すとき。 |
| 実ブラウザでの画面確認 | HTTP経路は確認済み。見た目とクリックは未実施。 | Designerが `http://127.0.0.1:8765/` を開くとき。 |
| GitHub Pagesの公開URL | 結果一覧と latest.html を Actions で公開する。 | https://ziriss8120121.github.io/hackathon-test/ |
