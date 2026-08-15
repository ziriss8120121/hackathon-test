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
| 既定モデル | `gemma3:4b`（Ollama経由） |
| 確認状況 | **未確認。** 確認した実機にOllamaが入っていないため、実際のモデル取得と利用規約の確認ができていない。 |
| 次にやること | Ollamaを導入した実機で `ollama pull gemma3:4b` を行い、モデルの利用規約と確認日をこの節に追記する。 |

この節が埋まるまでは、無料であることの確認は「依存パッケージとAPIについては完了、
モデルの重みについては未完了」の状態である。

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

## 6. 未確認のまま残っている項目

| 項目 | 理由 | 決める時期 |
| --- | --- | --- |
| Gemini無料枠の1日あたり上限 | APIキーを用意していないため未計測。 | GeminiBrainを実際に使うとき。AI Studioの使用量画面で確認して追記する。 |
| 実際のモデルでの所要時間とAI待機時間 | Ollama未導入のため未計測。要件NF-06の閾値はこの実測後に決める。 | M2の実機確認時 |
| モデルの重みの利用規約 | 上記4のとおり未確認。 | M2の実機確認時 |
