# diagrams

`docs/design.md` のmermaid図をPNGに書き出したものです。Confluence版の設計書がこの画像を参照します。

## なぜ画像が必要か

GitHubはmermaidをそのまま図として描画しますが、Confluenceは描画しません。そのためConfluence側だけ画像を参照します。図の正本は `docs/design.md` のmermaidコードです。

## 図と対応箇所

| ファイル | 設計書の該当箇所 |
| --- | --- |
| `01-architecture.png` | 2.1 全体構成 |
| `02-run-from-ui.png` | 3.1 画面から1試合を実行する |
| `03-speech-generation.png` | 3.2 1ターンの発言生成 |
| `04-vote-and-judge.png` | 3.3 投票、同数の決着、勝敗判定 |
| `05-failure.png` | 3.4 実行が失敗した場合 |
| `06-cli-series.png` | 3.5 コマンドから多試合を実行する |
| `07-result-view.png` | 3.6 実行環境を持たないメンバーが結果を見る |
| `08-game-phases.png` | 4.1 フェーズの状態遷移 |
| `09-run-status.png` | 4.2 実行状態の遷移 |
| `10-free-tier-exhausted.png` | 5.6 無料枠が尽きた場合 |

## 再生成

`docs/design.md` の図を変更したら、画像も作り直してConfluence版と揃えます。

```bash
python3 - <<'PY'
import re, pathlib
names = [
    "01-architecture", "02-run-from-ui", "03-speech-generation",
    "04-vote-and-judge", "05-failure", "06-cli-series",
    "07-result-view", "08-game-phases", "09-run-status",
    "10-free-tier-exhausted",
]
blocks = re.findall(r"```mermaid\n(.*?)```",
                    pathlib.Path("docs/design.md").read_text(encoding="utf-8"), re.S)
assert len(blocks) == len(names)
out = pathlib.Path("/tmp/mmd-src"); out.mkdir(exist_ok=True)
for name, body in zip(names, blocks):
    (out / f"{name}.mmd").write_text(body, encoding="utf-8")
PY

for f in /tmp/mmd-src/*.mmd; do
  b=$(basename "$f" .mmd)
  npx -y @mermaid-js/mermaid-cli@11 -i "$f" -o "docs/diagrams/$b.png" -s 2 -b white
done
```

図の数や順序を変えた場合は、上のリストと本READMEの対応表も更新してください。
