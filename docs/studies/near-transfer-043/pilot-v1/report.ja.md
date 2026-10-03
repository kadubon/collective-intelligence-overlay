# v0.4.3 pilot：assay_not_ready

locked入口ゲートを満たさず、confirmationは未実施です。H_ACC、H_CIO、H_FORM、
Full/Empty差、C/Mの追加価値、償却回数は未推定です。測定感度の診断であり、
方式の無効性・同等性の証明ではありません。

事前登録は2026-10-03 16:52:56 UTC、pushed commitは
`4f1403dfe1b5da022a8378ceb032c25faa950cd5`、branchは
`study/043-near-transfer-cost`です。推論時106 filesのsource、修正後reader、
最終0.4.3 native gateは別の証拠です。実験は公開済み非editable 0.4.2 wheel
（SHA256 `5d1ce6292a6519db8fc157cf9e34d277465c3380f76ed2a92a3b768bd9fac804`）
を使用しました。0.4.3はpackage実装bytesを保持し、配布metadataを更新します。

実モデルはGemma4:e4b、7.5B Q4_K_M、digest
`dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`、
Ollama 0.35.0です。CPU固定、context 4096、出力1024、temperature .2、
top_p .95、top_k 64、draft predictionなし、think=false、同時推論1、各要求は空会話。
終了時resident VRAMは0でした。pull、cloud、有料API、保存回答への置換はありません。

第1 waveは8 world、S1/S2・K1/K2・F0/F1の各候補4件で、すべて0/4でした。
同率規則でS1・K1・F0を選択しました。第2 waveは未使用6 worldで、結果から水準を
変更していません。

| locked family | 水準 | PASS/分母 | 目標 | 記述的exact 95%区間 |
| --- | --- | ---: | --- | --- |
| SQL | S1 | 0/6 | 30–70% | 0–45.93% |
| calibration | K1 | 1/6 | 30–70% | 0.42–64.12% |
| formation | F0 | 0/6 | 20–80% | 0–45.93% |

有限比率は潜在成功確率の精密な推定ではありません。共通pilot条件による依存が
あり得るため、binomial区間は記述用です。独立referenceは42/42、正常通信完結は
54/54でした。通信完結と解の妥当性・品質を区別します。失敗は意味不一致20、
program ValueError 19、OperationalError 2、不可視skill参照12です。
[全54 offered CSV](paired.csv)に成功・失敗をともに保持しています。

自然形成stockの到達検査は追加1 worldのM/C、各4学習episodeでした。両armとも
学習stockは空でした。新receiver qualificationと元provider物理停止後のprobeを
保持し、両family・両armとも未成功、検索された実行体0、各scratch推論1回でした。
これは経路検査であり、confirmationの独立NやC/M効果推定へ追加しません。

全stageで54要求、実測・chargeとも26,256 tokens、欠測0、driver実測wall
1009.437秒でした。先行サービス起動300秒予約は別記録で、保守的wall chargeは
1309.422秒です。隣接timerの小差があり、nested wallの加算ではありません。
model/observer cleanupは.593秒、両processは停止しました。
256 requests・400000 charged tokens・14400秒の上限を増やしていません。

| locked family | restricted秒平均 | restricted charged tokens平均 | 実probe wall合計 | 実tokens合計 |
| --- | ---: | ---: | ---: | ---: |
| SQL | 600.000 | 10240.000 | 69.874 | 2875 |
| calibration | 501.456 | 8601.333 | 54.468 | 2497 |
| formation | 600.000 | 10240.000 | 91.485 | 3478 |

失敗には共通600秒・10240 tokensの解析endpointを割り当てます。実消費とは異なります。
半horizon品質は既存prefixから算出し、推論を追加していません。成功者だけの比較は
一次指標にしません。形成・検証・保存・転送・setup・検索の原記録とinclusive wallを
保持し、親子wallを二重加算しません。将来保守、energy、完全compute・金銭ROIは
欠測です。有限の償却回数は主張できません。

原offline readerは既存APIの戻り値数、第1修正は不正SQLの例外分類で停止しました。
既存installed factoryを用いる修正後はonline拒否と一致し、原bytes・endpoint・分母・
推論数は変更していません。[reader修正履歴](reader-repair-provenance.json)とhashを
推論時sourceとは別に保存しています。署名・hashは悪意あるoperatorに対する
真実性の証明ではありません。[実数値](results.json)、[検算](verification.json)、
[方法](../../../near-transfer-043.md)を参照してください。

旧0.4.2のverifier/analyzerは各1回のみ実行し、公開結果と一致しました。Eの6組は
要求bytes・seed・options・空stockが同一でした。calibration出力差だけで不具合と
断定しません。旧raw・失敗・protocol・tag・配布物は書き換えていません。
