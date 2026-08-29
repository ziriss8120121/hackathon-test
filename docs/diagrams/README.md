# diagrams

`docs/design.md` のmermaid図をPNGに書き出したものです。Confluence版の設計書がこの画像を参照します。

## なぜ画像が必要か

GitHubはmermaidをそのまま図として描画しますが、Confluenceは描画しません。そのためConfluence側だけ画像を参照します。図の正本は `docs/design.md` のmermaidコードです。

## 図と対応箇所

設計書v2.3の図に対応します。図の順序は `docs/design.md` に現れるmermaidブロックの順序です。

図の数と順序はv2.0から変わっていませんが、`03-case-flow` と `09-game-phases` は内容が変わっています（ルール文書の反映）。v2.2とv2.3では図に変更はありません。PNGを生成する際は全11枚を作り直してください。

| ファイル | 設計書の該当箇所 |
| --- | --- |
| `01-architecture.png` | 2.1 全体構成 |
| `02-experiment-generation.png` | 3.1 実験からTrialと17ケースを生成する |
| `03-case-flow.png` | 3.2 1ケースを進行する |
| `04-free-discussion.png` | 3.3 自由議論の1ラウンド |
| `05-judge.png` | 3.4 Judgeによる事後評価 |
| `06-failure-resume.png` | 3.5 実行が失敗した場合と再開 |
| `07-analysis.png` | 3.6 分析出力を生成する |
| `08-result-view.png` | 3.7 実行環境を持たない閲覧者が結果を見る |
| `09-game-phases.png` | 4.3 ゲームフェーズの状態遷移 |
| `10-run-status.png` | 4.4 実行状態の遷移 |
| `11-free-tier-exhausted.png` | 5.7 無料枠が尽きた場合 |

PNGは現在このディレクトリに置かれていません。Confluence版へ図を載せる際に、下の手順で生成します。

## 再生成

`docs/design.md` の図を変更したら、画像も作り直してConfluence版と揃えます。

```bash
python3 - <<'PY'
import re, pathlib
names = [
    "01-architecture", "02-experiment-generation", "03-case-flow",
    "04-free-discussion", "05-judge", "06-failure-resume",
    "07-analysis", "08-result-view", "09-game-phases",
    "10-run-status", "11-free-tier-exhausted",
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
