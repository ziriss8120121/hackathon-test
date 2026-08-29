# runs

人狼テストの実行結果を置く場所です。

`playgrounds/mbti-werewolf` から実行すると、ここに自動で書き出されます。
手で作る必要はありません。

## 構成

実験 → Trial → ケースの3階層です。1ケースが8人ワンナイト人狼の1試合、
1 Trialが17ケース（混合構成1件と、16タイプそれぞれの同質構成16件）です。

```text
runs/
  e-20260901-210000/           実験（1回の実行）
    experiment.json            実験全体の条件と、Trialごとの結果
    status.json                実験の進捗
    experiment_metrics.csv     1行 = 1ケース
    t001/                      Trial
      trial.json               このTrialの固定条件。再開時に読む
      status.json              Trialの進捗
      trial_metrics.csv        1行 = 1ケース1プレイヤー
      c00-mixed/               ケース（混合構成）
        config.json            このケースの確定した実験条件
        status.json            進捗
        case_log.json          出力の正本。他のファイルはここから導出する
        transcript.md          会話全文とprivate memo
        summary.md             結果の要約（会話は載せない）
        result.html            自己完結の結果ビュー
      c01-ISTJ/ ... c16-ENTJ/  ケース（同質構成16件）
  latest.html                  直近に完了したケースの result.html への案内
```

`latest.html` はケースが1件終わるごとに更新され、直近の `result.html` へ自動で
切り替わります（切り替わらない環境用に手動リンクも出します）。ブックマークして
おけば、実験IDやケースIDを探さずに最新結果を開けます。

相対リンクなので、スマホやLINEから直接URLで開くには公開が必要です。
`runs/` をcommitして `main` へpushすると、GitHub Pagesの
https://ziriss8120121.github.io/hackathon-test/runs/latest.html
から同じファイルが開けます。

- 実験IDは `e-YYYYMMDD-HHMMSS`、Trialは `t001` から、ケースは `c00`〜`c16` です。
- ケースのディレクトリ名には構成種別が入ります（`c00-mixed`、`c01-ISTJ`）。

## 結果を見る

`result.html` をブラウザで開いてください。1ファイルで完結していて外部と通信せず、
スマホの画面幅でも表が折り返して読めます。Pythonを動かせなくても開けます。

会話の全文は `transcript.md`、結果の要約は `summary.md` です。数値を自分で集計
したい場合は `trial_metrics.csv` と `experiment_metrics.csv` を表計算ソフトで
開いてください。複数の実験分を縦に連結できます。

集計CSVには空欄の列があります。`final_entropy` と `convergence_round` はJudge評価
（設計書のM4、未着手）が入るまで空欄です。割合の列は、分母が0のときに0と区別する
ために空欄にしています。

## 注意

MBTIおよび心理機能は、実在人物の診断や評価ではありません。AIエージェントの
振る舞いを分けるためのフィクション設定として扱っています。

指標と勝敗の分析は暫定です。版によって変わります。
