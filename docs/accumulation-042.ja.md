# 0.4.2の縦断蓄積実験

実験の正本は[英語の方法・上限・再現コマンド](accumulation-042.md)、実際の実行状況は
[監査記録](audit-042.md)です。実装の存在、接続成功、独立品質のPASS、将来性能への効果を
区別します。第1校正はE/Mのconstructor鮮度維持の欠落により無効として保存しました。
全armの同期維持を実サービスで検査し、第2校正は新しいworldで完了しました。
校正中のsource・prompt・設定は固定し、全205推論・usage・DSSE/CAS・stock遷移を
socket遮断下で再検算しました。独立した3 worldの確認実験も完了し、全9 arm・669推論の
原記録をofflineで検証しました。0.4.2公開はまだ完了していません。

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

校正では各world×arm全体で64 model requests、655,360予約tokens、4,096 driver RPC、
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

第2校正は243,354実測tokens、欠測usage 0、約2.9時間でした。Mの学習stockは両worldで
空でした。当初のpooled low正答率は0.5ですが、実際はSQLの床と低難度校正の天井の平均です。
元の選択規則は保存し、別のfamily別レビューを事後検査と明記して`assay_insensitive`とします。
第3校正は行いません。蓄積状態の寄与は未判定です。

確認前の有限計画は、新しい独立world 3個×E/M/Cです。品質差MCIDと許容害は各5ポイント、
対比ごとの有界区間は99.5%、実施する8対比の多重性を管理します。432条件の精度計画を行い、
N=3では5ポイント差を十分な精度で判定できない`limited-power`と宣言します。
2 draftのtrainingと、最終評価の1/2 draft frontierを事前固定します。このtraining予算は
pilotで検証済みとは扱いません。9 arm全体のhard capは864 model requests・8,847,360 tokens、
推論並列度1、cohort wall 15時間、物理停止のgrace 300秒です。固定scheduleの最大draft数は723。
最終の実native gate・wheel/sdist・source・runtime・解析入力を結び付けてcommit/pushした後に
開始します。I/Aは実行しないためH_SHARE/H_ADAPTは未判定です。

形成成功は固定2 draftの方策で測り、900秒はrestricted time endpointの上限です。
失敗は900秒、遅い成功も900秒へ制限しますが、実際に消費したwallは別に全量保持します。
900秒のendpoint値を、物理停止時刻や実CPU消費とは扱いません。新しい合成能力について
別の未見formを検査しますが、その合成能力の新receiverへの移転は今回未測定です。
今回の有限課題分布の機能尺度から普遍的知能・持続的自己加速へ外挿しません。

offline verifierは原DSSE、CAS、request/response、usage、選択手順、実行、checker、
snapshotと全denominatorを検査し、推論を再送しません。これは信頼するlocal operator下の
整合性検査であり、model・物理processの暗号学的attestationではありません。
code/task generatorのApache-2.0、model terms、生成rawの由来を区別し、weights・秘密鍵・
operator configを公開しません。公開・確認の結果は実施後に原記録に基づいて追加します。

## 完了した校正の記録

2回目の校正は完了し、原記録をofflineで検証しました。
[日本語report](studies/accumulation-042/calibration-v2/report.ja.md)、
[英語report](studies/accumulation-042/calibration-v2/report.en.md)、
[解析表](studies/accumulation-042/calibration-v2/analysis.json)、
[検証結果](studies/accumulation-042/calibration-v2/verification.json)は実測からの派生物です。
[provenance](studies/accumulation-042/derivative-provenance-v1.json)が原byteとhashを対応させます。
205回・243,354 tokensの実推論を保持し、Mの学習stockは両worldで空でした。
当初のpooled校正規則の合格と、familyごとの事後レビューによる感度不足を分けて記録します。
精度計画・metadataのみのruntime観測は確認結果ではありません。
確認推論は完了しました。raw archive公開は未完了です。

## 独立確認の実測結果

確認protocol v2は最初の推論前にcommit/pushし、新しいseed 427319・619843・953117で
E/M/C各3 armを完了しました。[日本語report](studies/accumulation-042/confirmation-v2/report.ja.md)、
[英語report](studies/accumulation-042/confirmation-v2/report.en.md)、
[解析](studies/accumulation-042/confirmation-v2/analysis.json)、
[検証](studies/accumulation-042/confirmation-v2/verification.json)、
[実行集計](studies/accumulation-042/confirmation-v2/execution-summary.json)を保存しました。
原本と公開コピーのoffline解析は一致し、2回の失敗した検証と修正後の検証sourceを別々に保持します。

全510 offered課題、669 dispatch済み推論（E 181、M 244、C 244）を保持しました。
実測805,556 tokens、charge 815,796 tokensです。Mのdrift課題1件がReadTimeoutとなり、
final usageは欠測、10,240 tokensの上限予約を保持しています。cleanup込み総wallは34,897.687秒です。
既定並列度1、同じGemma/digest、同じ独立checkerとarm上限を維持しました。

最終anchorのQはC/Mが各3/18、Eが2/18です。C−Mは全worldで0ですが、99.5%の有界区間は
[-1, 1]、bootstrap区間は退化のため利用不能です。5ポイントのMCIDに対して精度が不足し、
同等性、利益の不存在、許容害以内という結論はいずれも出せません。
C/Mは全worldで学習stockを保持しましたが、full−emptyの品質差も0です。
無関連poolの実際の検索量が全offeringで対応していないため、full−irrelevantの因果対比は未判定です。

SQLの全難度と数値校正の中・高難度は床、低難度の数値校正はC/Mで天井でした。
宣言したfamily別の感度帯はありません。正解実行体10/10のpositive controlは校正専用です。
確認にoracleを入れなかったことを、oracle不合格という新観測へ読み替えません。
1/2 draft frontierでもC/MのQは1/6のまま、Eの記述的平均は1/9から1/6になりますが、独立Nは3です。

新構成の形成は全15 offered条件で未達でした。失敗のrestricted上限と実測費用を別に保持します。
学習手順の新receiver移転では元providerを物理停止し、新しいDB/CAS・空の会話から実行しました。
C/M fullは各3/6、emptyは2/6と1/6、E fullは0/6、emptyは3/6です。
少数の記述的差から移転効果を一般化せず、新構成の新receiver移転は未測定として残します。

H_ACC/H_CIO/H_FORMは精度・介入条件の制約により未判定、H_SHARE/H_ADAPTはI/A未実施です。
一部のfull評価でtokensが減っていても、初期形成・検証・移転・維持費と欠測computeを含む
総費用20%削減は確認していません。Eは介入offering数が少なく、全arm集計費用を主比較の
効率差として扱いません。結果はこのhost/modelと有限のsynthetic課題分布に限ります。
