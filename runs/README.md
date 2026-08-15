# runs

人狼テストの実行結果を置く場所です。

`playgrounds/mbti-werewolf` から実行すると、ここに自動で書き出されます。
手で作る必要はありません。

## 構成

1試合だけの実行も1試合のseriesとして扱います。多試合実行と構造を分けないため、
集計と画面の一覧処理が1本で済みます。

```text
runs/
  s-20260815-190959/         series（1回の実行）
    series.json              実行全体の状態と試合ごとの結果
    series_summary.md        試合数、勝率、心理機能別の集計
    r001/                    1試合
      config.json            この試合の確定した実験条件
      status.json            進捗。操作画面が1秒ごとに読む
      run_log.json           出力の正本。他のファイルはここから導出する
      summary.md             結果カード
      timeline.md            会話タイムライン
      metrics.csv            1行 = 1プレイヤーの集計
      result.html            自己完結の結果ビュー
```

- `series_id` は `s-YYYYMMDD-HHMMSS`、`run_id` は `{series_id}-r001` の形です。
- `run_id` が `series_id` を含むため、保存先は `run_id` だけで特定できます。

## 結果を見る

`result.html` をブラウザで開いてください。結果データを埋め込んだ1ファイルで、
外部と通信しません。Pythonを動かせなくても、ファイルを開くだけで読めます。

複数試合の傾向は `series_summary.md`、機能別の数値を自分で集計したい場合は
`metrics.csv` を表計算ソフトで開いてください。複数試合分を縦に連結できます。

## 注意

MBTIおよび心理機能は、実在人物の診断や評価ではありません。AIエージェントの
振る舞いを分けるためのフィクション設定として扱っています。
