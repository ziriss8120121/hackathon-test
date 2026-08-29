## 参加者

$participants

## 会話（文脈として読む）

$transcript

## 評価する発言

$batch

## 指示

「評価する発言」の$batch_count件について、それぞれラベル、言及した参加者、公開スタンスを答えてください。「会話」は文脈として読むだけで、評価の対象にはしません。

speech_id は「評価する発言」に書かれたものをそのまま写し、件数も順序も変えないでください。

次の形式のJSONだけを出力してください。

{"evaluations": [{"speech_id": "評価する発言のID", "labels": ["suspect"], "mentions": ["P4"], "stances": [{"target": "P4", "direction": "suspect", "strength": 2}]}]}
