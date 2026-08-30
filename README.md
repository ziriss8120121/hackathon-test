# MBTI × 人狼：AIエージェントによる集団意思決定シミュレーション

性格タイプが同じ集団と、異なるタイプが混ざった集団では、集団の判断はどう変わるのか。
MBTI×人狼のAIエージェントシミュレーションで検証しました。

## これは何か

本プロジェクトでは、MBTIタイプを設定した8体のAIエージェントにワンナイト人狼をプレイさせます。

1セットは、同じ実験条件で行う17試合で構成されます。

- 混合構成：異なるMBTIタイプが混ざった1試合
- 同質構成：1つのMBTIタイプで構成された16試合

この17試合を1セットとして、同じ人物・役職・ゲーム条件のままMBTI構成だけを変え、議論・判断・投票がどう変わるかを比較します。

今回は20 Trialを実行し、17試合が揃った18 Trial（306試合）を分析対象としました。

## 提出物

- GitHubリポジトリ：このページ
- 説明資料：[MBTI×人狼ゲームシミュレーション レポート（PDF）](https://www.dropbox.com/scl/fi/kyu31bh3s9yq4meoekhbi/0125_M-_mbti-werewolf_Report.pdf?rlkey=mnly0mbx36h3t30yyvuwd1z74&st=a2pmahg8&dl=0)
- デモ動画：`【ここにYouTube限定公開URLを入力】`

## デモの見どころ

1セット内の以下の2試合を比較します。

- 混合構成：`t001/c00-mixed`
- ESFP同質構成：`t001/c10-ESFP`

2つのチャットを同時に再生し、AIエージェントの議論から投票までの流れを確認できます。チャット終了後は、各ケースの勝敗・追放結果・判断の正誤と、2ケース間の結果の違いを比較します。

## 実験・分析

### Research Questions

- RQ1：混合構成と同質構成で、集団の意思決定はどう変わるか
- RQ2：同質MBTIタイプによって、集団の意思決定はどう異なるか

### 観察するもの

- 集団として人狼を追放できたか
- 意見や投票がどのように収束したか
- 議論によって判断を修正できたか

### 主な結果

- 人狼を追放できた割合は、混合構成33.3%、同質構成39.6%だった。差は限定的であり、構成の優劣は断定しない。
- 最終的な疑いは、混合構成より同質構成で特定の一人へ集中しやすかった。
- 同じMBTIタイプで構成された集団でも、人狼追放割合と疑いのまとまり方にはタイプ構成ごとの差が見られた。
- 疑いが一人に集中することは、正しい判断を保証しなかった。

詳細な分析結果、仮説との対応、今回できなかった分析は [`result.md`](docs/submission/result.md) を参照してください。

## 結果を見る

既存の実験結果は、以下から確認できます。

| ページ | URL |
|---|---|
| 実験結果一覧 | https://ziriss8120121.github.io/hackathon-test/ |
| 操作画面 | https://ziriss8120121.github.io/hackathon-test/simulator.html |
| 最新の試合 | https://ziriss8120121.github.io/hackathon-test/runs/latest.html |

`python -m mbti_werewolf pages` で静的サイトを生成します。

## リポジトリ構成

```text
.
├── README.md
├── docs/
│   ├── requirements.md
│   ├── design.md
│   └── submission/
│       ├── labeling-analysis-spec.md
│       ├── output-plan.md
│       └── result.md
├── playgrounds/
│   └── mbti-werewolf/
└── runs/
    └── 実験ログ・結果
```

- `docs/requirements.md`：要求定義
- `docs/design.md`：実装・分析設計
- `docs/submission/`：提出用の設計書・分析結果
- `playgrounds/`：シミュレーション実装
- `runs/`：実験ログ・結果

## 実行方法

詳細な実行手順は [`docs/design.md`](docs/design.md) を参照してください。

実験結果を生成すると、`runs/`配下に実行ログ・ケース結果・集計データが保存されます。

## 限界・今後の課題

本実験は、MBTIタイプを設定したAIエージェントによるシミュレーション上の探索であり、人間の性格や行動を直接検証したものではありません。

- Trial数が限られている
- LLMの出力や発言ラベルには揺らぎがある
- MBTIタイプによる因果関係は断定できない
- RQ2は探索的分析である
- 人間の性格や行動への直接的な一般化はできない

今後は、Trial数の追加、発言ラベルの全体分析、MBTI 4軸・心理機能の比較、統計的検定などを行います。

## ライセンス

依存パッケージのライセンスと料金区分は [`docs/free-stack-check.md`](docs/free-stack-check.md) を参照してください。
