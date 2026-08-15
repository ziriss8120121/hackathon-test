# hackathon-test

人狼テスト用のリポジトリです。

ここでは、AI開発の進め方、実行環境の制約、ログの残し方、GitHub Pagesでの共有方法を試します。

## 目的

- MBTI風の行動傾向を持つ人狼シミュレーションを一度動かす
- PC、AI利用枠、ローカルLLM、実行時間の制約を知る
- 結果をチーム全員が見られる形にする
- 本番に持ち込む実装パターン、ログ形式、画面の見せ方を見つける

## 置き場

| Path | 用途 |
| --- | --- |
| `docs/` | テスト用の補足メモ |
| `playgrounds/mbti-werewolf/` | 人狼テストの実験コード |
| `runs/` | 実行ログ、結果、画像 |

## スマホでの結果確認（GitHub Pages・未公開）

`runs/latest.html` は常に最新の試合結果を指すリンクだが、スマホやLINEから直接URLで開けるようにするには、この
リポジトリでGitHub Pagesを公開する必要がある（設計書のM6、2026-08-15時点で未着手）。
`https://ziriss8120121.github.io/hackathon-test/runs/latest.html` は、Pages公開後に使える想定のURLで、
現時点ではまだ404になる（`gh api repos/ziriss8120121/hackathon-test/pages` で確認済み）。

Pages公開は、リポジトリのSettings操作が必要なため人（Engineer）が行う。公開後は下記の手順で更新できる。

1. ローカルで試合を実行する（`runs/` 配下に `latest.html` と対象の `result.html` 一式が書き出される）。
2. `runs/` 配下の変更を commit・push する（ローカル実行しただけではURLには反映されない）。
3. 上記URLを開くと、pushした時点の最新結果が見られる。

## ルール

- 壊れてよい試作はここに置く。
- 本番提出用のコードはここに置かない。
- 課金API前提にしない。
- 使えた考え方だけを `hackathon-production` に移す。

