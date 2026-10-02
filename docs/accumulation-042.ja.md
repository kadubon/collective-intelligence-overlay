# 0.4.2の縦断蓄積実験

実験の正本は[英語の方法・上限・再現コマンド](accumulation-042.md)、実際の実行状況は
[監査記録](audit-042.md)です。実装の存在、接続成功、独立品質のPASS、将来性能への効果を
区別します。第1校正はE/Mのconstructor鮮度維持の欠落により無効として保存しました。
第2校正の前に全armの同期維持を検査しています。確認実験・0.4.2公開は未実施です。

## 検証する問い

同じモデル・情報・総資源・品質基準で、経験から形成した実行可能な手順を保持・共有すると、
未見課題を空の会話状態や新receiverで処理する能力が改善するかを測ります。
Eは課題を越えた手順を渡さず、Mは通常の強い共有skill記憶、CはそれにCIOの独立証拠・
適用条件・現在の受入判定を加えます。主比較はC−Mです。full−emptyによる蓄積一般の寄与と
混同しません。I（private保持）とA（局所適応配分）は別panelの設計対象であり、未実施なら
共有・適応の命題は未判定とします。

## 実験単位と状態介入

独立単位は固有の潜在規則・データ・schemaを持つworld全体です。同じworldのtask・peer・
checkpoint・model callを独立標本として数えません。実Gemmaを使う2 proposerがそれぞれ
SQLと数値校正の異なる経験を持ちます。同じhost/modelを使うため独立組織とは主張しません。

6 training episodesを通して手順を保持し、0/3/6の固定checkpointで同じ難易度構成の
未使用6形式を評価します。モデルへ渡す会話は毎回1つの新しいmessageです。評価結果・
隠れた正解・評価会話はtraining stockに戻しません。

最終checkpointでは同じ問題・checker・model seed・オンライン予算でfull、empty、
irrelevantの順を事前に無作為化します。emptyが消すのは学習に使える手順だけです。
安全ledger・鍵・権限・撤回履歴は保持します。古いprovider、binding、回答cacheへ抜ける
model tool経路はありません。irrelevantは別の潜在worldで実モデルが形成し、独立検査を
通った実体から、型・件数・版・手順のbyte量を合わせます。不足したmatchはそのまま
記録し、training poolを無関連だと偽装しません。空のstockは寄与を識別できません。

## 課題と新能力形成

SQL課題はdedupの順序、時刻・欠測・refund、複数表join、有効期間付き単位変換、rebateを
組み合わせます。専用のメモリ内fixtureだけを、SQLite標準authorizerと時間・行数・
実行step上限付きで読みます。本番PostgreSQLへ任意SQLを渡しません。

別familyは有限の公開観測から校正多項式を作り、未見の値へ適用する課題です。
低・中・高難易度と、未知の集約、drift、再利用余地の小さいnegative controlを残します。
後続形成probeでは新readings connectorをSQL・校正・集約で合成します。モデルがSQL・
係数だけでなく演算順序を選び、実MAF workflowを実行します。誤った順序では独立品質が
変わります。完成した合成手順は初期poolに入れません。

新receiverは別鍵・空のDB/CASで始め、原artifactと署名をimportし、別のqualification形式で
ローカルbindingを再検証します。その後で元の2 proposerを物理的に停止し、未見transferを
測ります。元の会話は渡さず、import、検証、維持、失敗の費用も残します。

## 校正、資源、解析

第1校正は確認用と異なる2 worldのE/Mと、完全に別のpositive-control領域を使います。
E/M正答30–80%、control 90%以上、完結しusageを取得した応答90%以上を感度の目安にします。
C−Mの符号では選びません。校正は最大2 cohort、変更時は新protocol IDを使い、原失敗を
置換しません。確認最初の要求前にsource・model・seed・caps・解析・実wheelを固定して
commit/pushします。必要Nを満たさない有限cohortはlimited-powerと事前に明示します。

各world×arm全体で64 model requests、655,360予約tokens、4,096 driver RPC、
4,096予約実行、1,024 checker cases、80 retrievals、10,000秒を上限とします。
cohort上限は12時間、model並列度は1です。stock 128 KiB、検索3手順/10,000 bytes、
prompt 20,000 bytes、各owner CAS 16 MiBも固定します。実応答と同じusageを使い、
欠測は予約上限と実測不明を分けます。起動前からOS観測を行いますが、短命process CPU、
共有WSL PostgreSQL CPU、GPU counter、energyは完全には取得できません。
API料金が0でも計算費が0とは扱いません。

解析はworld単位のpaired bootstrapと、退化時にも残る保守的な有界区間を併記します。
主要指標は最終QのC−M、蓄積介入と新形成は別指標です。未達形成も打切りとして残し、
初期形成投資を含めます。失敗の900秒endpoint chargeは実測wallへ置き換えません。
非有意・bootstrap[0,0]を同等性へ読み替えず、未実施panelや精度不足は未判定とします。
今回の有限課題分布の機能尺度から普遍的知能・持続的自己加速へ外挿しません。

offline verifierは原DSSE、CAS、request/response、usage、選択手順、実行、checker、
snapshotと全denominatorを検査し、推論を再送しません。これは信頼するlocal operator下の
整合性検査であり、model・物理processの暗号学的attestationではありません。
code/task generatorのApache-2.0、model terms、生成rawの由来を区別し、weights・秘密鍵・
operator configを公開しません。公開・確認の結果は実施後に原記録に基づいて追加します。
