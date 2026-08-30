公開議論が終わりました。投票の前に、あなたの現在の考えを記録します。この回答は他の参加者には公開されません。

## ここまでの公開発言

$speech_log

## 指示

次の形式のJSONだけを出力してください。

{"suspect": "最も疑っている参加者", "confidence": 4, "reason": "その判断の理由を1文・40字以内", "planned_vote": "投票する予定の参加者"}

- `suspect` と `planned_vote` に指定できるのは $candidates です。ここでは `unknown` は使えません。最も疑っている相手を1人挙げてください。
- `planned_vote` は `suspect` と同じでなくてもかまいません。
- `confidence` は自信の度合いを次の5段階から選びます。

$confidence_scale
