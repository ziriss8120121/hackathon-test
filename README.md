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

## 結果の公開（GitHub Pages）

| ページ | URL |
| --- | --- |
| 一覧 | https://ziriss8120121.github.io/hackathon-test/ |
| 最新の試合 | https://ziriss8120121.github.io/hackathon-test/runs/latest.html |

`main` へ push すると GitHub Actions が `runs/` から静的サイトを作り直す。
ローカルで試合を回しただけではURLは変わらない。操作画面からの新規実行は公開しない。

## ルール

- 壊れてよい試作はここに置く。
- 本番提出用のコードはここに置かない。
- 課金API前提にしない。
- 使えた考え方だけを `hackathon-production` に移す。
