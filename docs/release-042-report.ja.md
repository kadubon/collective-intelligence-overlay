# 0.4.2実装・監査・公開の最終報告

0.4.2の実装、宣言したnative候補検証、実Gemmaによる独立確認、原記録の公開、
実PyPI導入および公開assetの再ダウンロード検証を完了しました。
科学的にはCIOの優越性も同等性も確立していません。実装・公開の成功と仮説の判定を分けます。
機械可読の実際の状態は[release-042-results.json](release-042-results.json)、
方法・全上限は[英語方法書](accumulation-042.md)、実測は[日本語結果](accumulation-042.ja.md)です。
この報告はimmutable tag後のmainに追加し、tagや研究archiveを書き換えていません。

## 1. 旧0.4.1原記録と補完範囲

保存原本と実際に取得した公開rawをsocket遮断下で再検算し、30 pair・60 arm・
360 offered/PASS・180実推論が一致しました。全armの品質は1で天井、適応−固定の差は0です。
generated tokensは固定2,227、適応2,244、平均active wallは50.9598秒と52.6887秒でした。
旧実験は各episodeで状態をresetするため、縦断蓄積の証拠ではありません。
今回補完したのは原byte、usage、署名/CAS、実行リンク、元仮登録と公開コピーの整合性であり、
過去の物理実行や悪意あるoperatorに対するattestationではありません。
旧tag、配布物、zero-effect結果、raw checksumを保持しています。

## 2. CIO-041-01の再現・修正・回帰

修正前は実PostgreSQL/OPA/認証済みA2Aでworkerをkillすると、dispatch時点および実provider
完了後にUNKNOWN/held・receipt欠落が残り、同じIDの再送は再実行しない一方、owner reviewも
欠落receiptのため拒否し、有限capacityを回復できませんでした。
既存ledgerへacceptance/dispatch anchorを原子的に保存し、v6のreceiptless owner recoveryを
追加しました。legacyには現在の観測を残し、過去のworker receiptや系譜を創作しません。
正確なrequest、binding、全有限descendants、実result/effect、物理的静止のread-only reviewを
要求します。closureは現在のcapacityだけを解放し、過去UNKNOWN・held予算を保持します。

固定sourceで48回帰、9物理kill事例、511署名record、258 anchor、9 closureを保存しました。
並行close、容量32、replay、dump/restore、local/remote子、応答欠落、部分effect、動作中worker、
偽quiescence、改ざんを含み、必須skipなしで通過しました。native fault profileも検証済みです。
完全性は登録した有限照会と信頼するDB/運用基盤に依存します。migration 0022・wire v6への
offline更新では古いreader/writerを停止します。rolling互換性は宣言しません。

## 3. 実装・OSS・依存・ライセンス

MAF、公式A2A/MCP SDK、PostgreSQL、SQLAlchemy/Alembic、OPA、既存DSSE/暗号形式を再利用しました。
ownerの業務上の回復条件はSDKの通信完了だけでは表現できないため、最小のledger/projectionを
追加しました。課題生成、cognitive view、介入、独立checker、world単位の解析はpackage外です。
汎用agent runtime、独自workflow DSL、中央managerは追加していません。
0.4.1→0.4.2のpyproject差分はversionのみで、runtime依存宣言は増やしていません。
Python>=3.12・Apache-2.0を維持します。実際の各導入環境のlicense/SBOM・advisory auditを保存しました。
Gemmaのmodel termsとraw生成物の由来はcode licenseと分離し、weights・秘密鍵・operator configは
公開物から除外しています。synthetic fixtureとtask generatorの由来をarchiveに明記しました。

## 4. 校正の全試行と独立確認の固定

smoke v1–v4をすべて保持しました。v1は推論前のpath障害、v2はusage欠測、v3は列順の
不適合、v4は接続検証であり、効能の標本ではありません。
校正v1はE/Mのconstructor鮮度維持の欠落で無効でした。208観測のうち17 dispatch、
191は正の未送信証拠を持ち、16完結、1 usage欠測です。実測17,885、charge 28,125 tokensを保持しました。
校正v2は別worldのE/M、4 arm・205完結推論、243,354 tokensで完了しました。
Mの学習stockは両worldで空でした。元のpooled low選択規則は0.5で通過しましたが、
family別の事後レビューではSQLの床と低難度数値校正の天井の平均で、測定感度が不足していました。
正解実行体controlは別領域で10/10、確認armへ流入させていません。C−Mの符号で選びませんでした。
校正上限2回を守り、第3校正を行っていません。

確認v1起動はmetadata順序guardで停止し、推論・offered課題とも0でした。
確認v2は`ca4f7e412349f2068c32e26ac620883045a21742`を最初の推論前にpushし、
protocol SHA256 `16319b4376542abe159080bca1993b6153cd018a6355a920c4a0ca93d33f788c`、
seed 427319/619843/953117、E/M/CのLatin順、source100ファイル、実候補wheel、model/runtime、
上限と解析を固定しました。事前からN=3のlimited-power確認と宣言しています。
完了後の検証は32 MiB aggregate制限、qualification予約lookupで2回失敗し、原失敗を保存しました。
verifierだけを9cdcb6bで補正し、128 MiBの有限aggregate制限と全事前schedule予約を検査しました。
generator/prompt/checker/model/schedule/statisticsや原記録を変えず、推論を再実行していません。

## 5. 実model・host・設定・usage・上限

Gemma `gemma4:e4b`、digest
`dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`、
7.52B・Q4_K_MをOllama 0.35.0で実行しました。専用loopback 11443、cloud無効、並列1、
CPU resident・VRAM 0でした。hostはWindows 11 Home 10.0.26200、Ryzen 7 8840HS（8C/16T）、
OS RAM 66,363,183,104 bytes、AMD Radeon 780Mです。
`num_ctx=8192`、`num_predict=2048`、temperature .2、top_p .95、top_k 64、
draft_num_predict 0、think false、request上限240秒を固定しました。
MAF core 1.19.0、Ollama provider 1.0.0b260813、ollama .5.3を使用しました。
PG 16.15、OPA 1.21.0、Caddy 2.11.4+cio.1の実体とhashも保存しています。

確認は実測805,556 tokens、charge 815,796 tokens、cleanup込み34,897.687秒でした。
欠測1件へ10,240 tokensの上限予約をchargeしました。料金0を計算費0とは扱いません。
9 arm上限は864 model requests・8,847,360予約tokens・cohort 54,000秒と停止grace 300秒、
各armは96 requests・983,040 tokens・12,000秒です。driver/execution/checker/retrieval/CAS/stock/
promptにも有限上限があります。4,905 OS samplesは保存していますが、短命process CPU、共有WSL、
GPU、energyの完全費用は取得できず、総費用20%削減やbreak-evenは未判定です。

## 6. 群・独立world・失敗・欠測

確認の独立単位はworld全体でN=3です。各worldにE/M/Cを1 armずつ置き、9 armを完了しました。
同一worldの課題やmodel callsを独立標本に増やしません。

| 群 | arm | offered | dispatch | 完結応答 | 実測tokens | charge tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| E | 3 | 132 | 181 | 181 | 214,288 | 214,288 |
| I | 0 | 0 | 0 | 0 | 未実施 | 未実施 |
| M | 3 | 189 | 244 | 243 | 295,615 | 305,855 |
| C | 3 | 189 | 244 | 244 | 295,653 | 295,653 |
| A | 0 | 0 | 0 | 0 | 未実施 | 未実施 |

計510 offered、669 dispatch、668完結応答です。Mのdrift 1件がReadTimeoutでfinal usage欠測です。
失敗形成、negative control、drift、censoring、usage欠測は保存し、PASSへ変換していません。
Eは介入offering数が少ないため、群全体の消費をmatched主比較の効率とは扱いません。

## 7. 仮説を個別に判定

| 命題 | 観測と判定 |
| --- | --- |
| H_ACC | C/Mは全worldで非空stockを保持したがfull−emptyの最終品質差0。測定感度・精度不足。irrelevantの実retrieval doseが一様に対応せず、その因果対比は未判定。 |
| H_CIO | 最終anchorはC/M各3/18、E 2/18。C−Mは各worldで0。優越性、同等性、有意味な利益の否定、許容害以内は未確立。 |
| H_SHARE | I未実施のため未判定。 |
| H_ADAPT | A未実施のため未判定。 |
| H_FORM | 新構成15 offeredすべて未達。この条件で加速を観測せず、比較効果・一般化・新構成の新receiver移転は未判定。 |

## 8. 区間・精度・多重性・分布の限界

C−Mの99.5%独立world有界区間は[-1,1]、bootstrapは退化して利用不能です。
MCID・許容害は各.05、8対比をBonferroni/Holmで扱いました。p-bound 1や非有意を同等性へ
読み替えません。N=3では5ポイント差に対する精度が足りません。
SQL全難度と数値校正の中・高は床、低難度数値校正はC/Mで天井で、宣言したfamily感度帯はありません。
期間は6 training episodesと有限checkpoint、単一host/model、syntheticなSQL/数値校正課題に限ります。
1/2 draft frontierでもC/M Q=1/6、Eの記述平均は1/9→1/6ですが、独立Nは増えません。
普遍的知能、持続的自己加速、異なる組織/モデル/業務への外挿は行いません。

## 9. 空context・新receiver・新能力形成の実測

会話を毎回新しくし、readonly評価をtraining stockへ戻さず、full/emptyを比較しました。
新receiverは別鍵・空DB/CASから原artifact/署名をimportし、別qualificationを実施しました。
元providerを物理停止した後のtransferはC/M full各3/6、emptyはC 2/6・M 1/6、
E full 0/6・empty 3/6でした。少数の記述差を一般的移転効果とは結論しません。
全新構成形成が未達で、その新receiver移転は未測定です。stock件数やdigest数を知能と呼びません。

## 10. GitHub・PyPI・raw・checksum・再計算の実際の状態

annotated `v0.4.2`はcommit `abbc7bbf000dc6fe2eb43477f212156aa388f133`、
tag object `7dcd9d923fb86986caf0b41de0fa7331f46112a5`です。
[元native gate 37126141569](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37126141569)は
12 native・4 cross reader・mixed Python・readyに成功し、原3,819ファイルと候補hashを照合しました。
全nativeのsource 778件・installed agents 772件に失敗/error/必須skipはありません。
従来の長時間本番profileは過去の証拠として保持し、0.4.2の新しいlong soakと呼びません。
[tag/OIDC公開37133055121](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37133055121)は
標準selectorで同じwheel/sdistを復元し成功しました。再build、tag移動、skip-existing、
0.4.1限定recovery例外の流用をしていません。

[PyPI 0.4.2](https://pypi.org/project/collective-intelligence-overlay/0.4.2/)の実bytesが候補と一致しました。
Windows CPython 3.12.14/3.13.15/3.14.7のcore/agents/model/Ollama計12新規導入構成で、
通常解決、公開rootを含むadvisory audit、license/SBOM、unit/provider/rebuilt-sdistを検査しました。
別の新規導入から実PG/OPA/MCP/A2A 3プロセスdemoでACCEPT・117.00・REQUALIFY・REJECTを確認しました。
HTTP stubのSDK試験を実model推論に数えていません。

[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.2)の全10 assetを
実際に再ダウンロードし、hash・sizeを照合しました。`SHA256SUMS.txt`に自己を除く全assetを載せています。
研究archive `cio-042-evidence-v1.zip`は298,576,015 bytes、SHA256
`c3698feb03ef32bc06fc5ad6ba25b3c1c9e7383880c8ab53aadcc07f5cd96a24`です。
23記録群、38,473対応hash、38,615収録ファイルを保持し、元raw/CAS/DSSEとmetadata redactionを分けました。
実downloadから確認原記録を展開し、socket遮断下のverify/analyzeで公開済み検証・解析と完全一致しました。
[再計算証明](studies/accumulation-042/public-download-reproduction-v1.json)を保存しました。
公開後導入証明は別archiveで、凍結した研究archiveを書き換えていません。

## 11. 未実施・blocker・次に必要な独立検証

宣言した実装/native/公開/実PyPI導入/公開raw整合性検証に未解決blockerはありません。
I/A、doseが対応するirrelevant因果比較、新構成の新receiver移転、完全compute/energy、一般化や
十分な精度の効能判定は未実施または未判定です。対象スキャンは完全な外部privacy/security監査ではありません。
次の研究は別protocolとして、中間感度帯を持つfamily、実retrieval dose対応、成功し得る新構成、
必要な独立world数と費用計測を先に校正・事前登録し、別host/receiver/業務分布で検証する必要があります。
今回の原失敗や負の結果を上書きせず、今回内の第3校正や有利なseedへのrerollは行いません。
