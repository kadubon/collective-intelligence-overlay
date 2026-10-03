# v0.4.4 有限の意味選択による SQL/formation 測定

[完全な方法・protocol](bounded-scratch-044.md)と
[実測報告](studies/bounded-scratch-044/results-v1/report.ja.md)を参照してください。
対象は自由 SQL や任意プログラム生成ではなく、有限の意味選択から実行手順を構築・
保存・転用する限定課題です。製品 core の一般的な拡張契約は変更していません。

| Family | モデルが選ぶ意味 | 公開契約から host が固定する値 |
| --- | --- | --- |
| SQL L0/L1/L2 | 負数方針、null 方針、終端境界を順に追加 | 表・列・引用 alias、parameter binding、sum、未出力の宣言済み方針 |
| Formation L0/L1/L2 | affine と sum の順序、net/gross mapping、unit/double scale を順に追加 | インストール済み抽出・変換・集計部品、公開 offset/slope、MAF builder |

モデル出力は必須 enum 1–3 個だけです。SQL 本文、係数、説明、skill ID は生成しません。
未出力値を private oracle から補完しません。2/4/8 候補はすべて構文実行でき、独立
Decimal checker と witness が意味差を識別します。隠れた入力は新 group・別数値範囲です。
同じ schema・部品・builder を M/C・Full/Empty へ与えます。

G0 は有限な非モデル検査、全候補の実 builder/checker、実 Gemma の短い smoke 4 要求です。
公開 SDK HTTP 直列化では全 6 schema を synthetic 応答で確認し、実モデルで訪問した
L1/L2 の 4 schema と区別します。未訪問 L0 を実モデル検証済みとは扱いません。

G1 は L1 から各設定 8 要求で開始し、0–1/8 なら意味 slot を減らし、6–8/8 なら増やします。
2–5/8 のときだけ選定し、床・天井の端点を選定しません。設定の再訪や C−M による選定は
禁止です。今回両 family が L2 の天井に達し、選定なしで停止しました。

G2 は選定済み設定だけを未使用 12 world/family、6 件ずつ 2 ブロックで再確認します。
3–8/12、両ブロックの成功・失敗混在、全正常通信・schema・構文実行、独立 random/constant
対照を上回る観測が必要です。今回は未開始です。少数の広い区間から真の成功確率が
20–70% 内と証明したとは言いません。

G3 は G1/G2 の実 Gemma 合格候補を同じ原応答のまま M/C の別履歴へ渡す到達性診断です。
新 receiver の import・独立 qualification、元 provider 停止、再起動後の同じ
artifact/binding、Full の receipt、Empty の scratch 到達を確認しました。追加推論は
Empty の計 4 件で、Full はゼロです。同じ候補の M/C 複製を比較効果や初期 confirmation
stock に使いません。

全 G0–G3 が成立した場合だけ、別に push した前向き protocol で 6 未使用 world の
M/C × Full/Empty、arm ごとの自然学習 stock、near/formation 一 draft 比較へ進みます。
空 stock の world も除外しません。今回その条件を満たさず、比較は未実施です。

共通上限は 256 要求、未確定 reservation を含む 400000 tokens、setup/cleanup を含む
14400 秒、同時実行 1。実 model/digest/options を固定し、所有 process だけを制御します。
未成功への T=300 秒/B=4352 tokens は restricted 評価値で、実消費とは別です。
固定費・オンライン offer・総 inclusive wall・nested RPC を区別し、energy・全 compute・
将来保守は欠測として残します。正の節約が観測されていないため償却点は求めません。

実行コマンド、必要な通常 installed 環境・PostgreSQL/OPA/Caddy、原記録を変更しない
offline reader は[英語の方法](bounded-scratch-044.md#commands)にあります。
旧 0.4.3 の 53 失敗と採点、protocol、tag、配布物は保持しています。
