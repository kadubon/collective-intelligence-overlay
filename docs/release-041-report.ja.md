# 0.4.1 監査修正・ローカル Gemma 評価の実行記録

実モデル評価、監査回帰、全 native/cross/mixed/ready、OIDC 公開、実 PyPI の通常 install、
公開後検査と raw upload が完了しました。[実結果 JSON](release-041-results.json) が各 source と hash を記録します。
原記録と否定的・失敗した試行は保持しています。

## 1. 監査 6 件

| 指摘 | 修正と実サービス回帰 | 残る境界 |
| --- | --- | --- |
| CIO-040-01 | 通常完了と照合で保存済み依頼の ID・outbound 主体・provider・binding・arguments・purpose・実 result digest を共通検査。実 A2A の不整合応答 12 ケースを拒否 | 整合した応答も真実性の証明ではない |
| CIO-040-02 | owner actor と original caller を別指定。C→B→A、B 再起動、応答喪失、B による C namespace の照合、他主体の拒否を実 3 process で確認 | 元 mapping/ID を維持。C に B の全履歴を開放しない |
| CIO-040-03 | owner の全作用・結果・physical quiescence review と署名 resolution、migration 0021 の投影を追加。実 DB の既定 32 件、partial/absent/unknown、並行 close/claim、restore、撤回を確認 | 過去 UNKNOWN、held allowance、旧署名を維持。受付枠回復は refund・再実行・品質 PASS ではない |
| CIO-040-04 | 適用性を evidence support・source freshness・期限に共通適用。実 PostgreSQL/OPA で対象外証拠と関連 FAIL/撤回/期限切れを比較 | 関連する反証や同期未完了は引き続き拒否理由 |
| CIO-040-05 | 同 volume の staging、active writer lock、孤立書込み回収と旧残骸 quarantine。Windows/Linux の kill、backup、restore、capacity、並行 writer を確認 | 全 native 最終候補検査も通過。process kill は電源断耐性の証明ではない |
| CIO-040-06 | 型付き backup inventory と必須参照、PGDMP・bounded pg_restore inspection。29 構造/条件ケース、実 restore、旧 migration を確認 | checksum・構造・実復元・外部照合を分離。unsigned manifest は authenticity anchor ではない |

実装箇所と回帰は [監査 register](audit-041.md) と
[全試行 catalog](audit-041-status.json) を正本とします。
MCP 2.2.0 の JSON 受信上限の欠落は実 SDK で確認し、公開 HTTP hook に
byte/depth/time/tool-list 上限を設けました。13 実受信 probe が通っています。
v0.4.0 の初回正式 duplicate-soak の根本原因は未確定です。有限な診断の成功を
根本原因の解消とは扱いません。

## 2. OSS・license

core の新しい必須依存は追加していません。MAF core 1.19.0、A2A SDK 1.1.5、
MCP/mcp-types 2.2.0、HTTPX 0.28.1、HTTPX2 2.13.1 を既存公開 API で使用します。
新 optional provider は agent-framework-ollama 1.0.0b260813 と ollama 0.5.3（MIT）、
解析用 SciPy 1.18.1 / NumPy 2.5.3 は development 依存です。
PostgreSQL 16.15、OPA、監査した Caddy v2.11.4+cio.1 を実サービスに使用しました。
各 binary/module/依存の条件と NumPy の補助 notices は
[compatibility](compatibility.md)、NOTICE と license/SBOM 原記録を参照してください。

新規コードは Apache-2.0。インストール済み exact model の `/api/show` と
matching digest の公式 model ページには Apache-2.0 が記載されています。
weights は再配布していません。synthetic generator のコードと raw model 出力の
観測記録を同じ license と自動的に扱っていません。

## 3. 自前実装と CI

保存依頼との業務整合性、owner resolution、backup 構造、CAS crash 境界は
SDK が決められない owner policy の接続部分です。モデルを別 runtime へ抽象化せず、
公開 MAF Ollama client の観測 wrapper と finite tabular application を加えました。
tag v0.4.0 との差分は package 22 files、追加 2,696 / 削除 156 physical lines。
候補 1fd790d の tracked Python physical lines（空行・comment 込み）は
package 19,148、scripts 8,506、tests 19,731、examples 700 です。
resolution は 535、tabular application は 884、observer は 245 lines。
配布外の公開再開 guard は別に 137 Python physical lines、回帰は 159 lines。
新 agent framework、workflow DSL、broker、暗号方式、共有 manager は作っていません。

重い hosted 検証は以下の節目に分けました。通常 push は quick のみで、
hosted runner では model を実行・download していません。

| Run | 目的・実際の状態 |
| --- | --- |
| [36962813882](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36962813882) | 代表 Linux checkpoint。488/489 source pass。古い理由文字列の期待が失敗。原本保持後に exact reason と actuator 拒否をローカル確認 |
| [36965233400](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36965233400) | 初回 full。11 native は 489/489 source pass。Mac Intel 3.12 は pressure fixture で 488/489。旧 0.4.0 report identity も 0.4.1 を拒否。installed gate 未到達 |
| [36973489591](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36973489591) | 版別 profile と実同期 prerequisite を修正した full。全体成功。12 native・4 cross・mixed・ready が通過。各 source 506、installed agents 500、model 1、Ollama 5、sdist 103、skip 0 |
| [36984866375](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36984866375) | 初回 immutable tag。candidate は通過、ready の shallow checkout が元 ancestor を取得できず停止。publish 未実行 |
| [36986961717](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36986961717) | 固定 tag・全原 gate の照合に成功。省略した native job の状態を公開 job が継承し publish skip。原記録保持 |
| [36987219345](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36987219345) | 明示的な candidate・ready・quick 成功条件に修正した既存 workflow/pypi/OIDC。全体・publish 成功。同一 bytes、原 native gate、固定 tag、実 recovery engine を別々に束縛 |

旧 profile の数値や失敗 report は変更していません。新 native profile も 19 injections、
3 owners、120 秒以上・600 秒未満です。53 分かかった Intel source suite と installed suite を
収容する CI job の上限は 150 分で、実行や fault protocol の上限とは別です。
local corrected fault 経路は 1 pass / 436.19 秒、protocol elapsed 415.7126 秒。
aged-observation probe の UNKNOWN/released/admission_denied は無 dispatch でした。
実署名同期後は UNKNOWN/held が既定 32 件で停止します。先行する待機 probe の timeout と
key positive-control の freshness 失敗も別の原本として保持しています。
local quick は 48 pass。53 JUnit 原本は反復を含み、独立な標本数とは扱いません。
recovery guard と既存 gate の local 29 件も通過。実 depth-one clone の祖先欠落と、
tag object を動かさない full fetch による解消、別 ref/actor/source/candidate 拒否を確認しました。
初期からの quick は `36962814542`、`36963417802`、`36965233551`、`36965531468`、
`36973489879`、`36984649137`、`36986834541`、`36987091988` の 8 回成功。
重い hosted は代表 1 回と full 2 回。tag/再開で重い native/model は再実行せず、
全報告 hash と元 successful run を照合しました。recovery engine は元 native source と別です。

## 4. 実 model / hardware

Ollama 0.35.0、exact `gemma4:e4b`、digest
`dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`。
Q4_K_M、7.5B、installed 6,583,656,505 bytes、CPU llama.cpp/llama-server。
Windows 11 build 26200、Ryzen 7 8840HS（8 cores/16 threads）、RAM 66,363,183,104 bytes。
Radeon 780M driver 32.0.21010.10 は存在しますが GPU は使用せず、API `size_vram=0`。
WMI の AdapterRAM 表示を実使用可能な dedicated VRAM と扱っていません。

専用 loopback server に `OLLAMA_NO_CLOUD=1`、実 log で cloud disabled=true。
既存 Ollama、別 models、設定を変更していません。pull、paid/cloud/fallback は未使用。
要求設定は context=4096、num_predict=512、think=false、draft=0、temperature=.2、
top_p=.95、top_k=64、keep_alive=5m、並列 1、25 秒/request、retry 0。
resident context=4096 は観測しました。返されない engine 実効設定は未確認と分けています。
185 点の補助 OS 観測は開始が遅く、process-lifetime peak working set 8,509,886,464 bytes。
whole-run/arm 別 CPU・全 descendant RSS・energy は完全には測定していません。
API fee=0 は local compute cost=0 を意味しません。

## 5. 事前登録と全試行

[Preregistration](experiments/gemma-041/preregistration-v1.json) は最初の request 前に
commit/push した `35245df2bc902f52524916f10891f16cfb4904c4`、SHA256
`b8dff43a48deab2d3a7d0f5d3aec6657b8ab356eb42244fa141e608456a2763d`。
corrected pilot は 5 pairs / 60 tasks / 30 model requests、確認用は別 seed の固定
30 pairs / 60 arms / 360 offered tasks / 180 requests、elapsed 3,277.0687 秒です。
後者は limited-power exploratory assessment と事前宣言し、N を増減していません。
各 arm は最大 4 requests、18,432 upper-reserved tokens、600 秒。
全体の事前上限は 1,105,920 tokens と 36,060 秒で、実総 token は 58,947 です。

実行時 source 81 files、checker・generator・prompt・model・依存・wheel を固定しました。
候補は clean environment の 66 locked distributions に install し、全 package bytes を照合。
後の CI fixture/profile 修正はこれら 81 files と package/README を変えていません。
検証 gate の差分は、評価後に bytes が変わった 10 files、新しい 4 files、
bytes が同じで今回 hash を束縛した既存 101 files を区別しています。
事前登録に未記録の hash は、元 commit から事後照合した値として明示しました。
3 peer identities は同じ model を共有し、3 独立組織・知性ではありません。
source/ setup failure、allocation-only pilot、task smoke、tampered verifier test を
主 cohort へ混ぜていません。

## 6. 主結果と限界

| 指標 | Static | Adaptive |
| --- | ---: | ---: |
| heldout pass / offered | 180/180 | 180/180 |
| input / generated tokens | 27,238 / 2,227 | 27,238 / 2,244 |
| mean inclusive active wall（秒） | 50.9598 | 52.6887 |
| mean cleanup 込み wall（秒） | 53.6488 | 55.4909 |
| missing usage / UNKNOWN / false accept | 0 / 0 / 0 | 0 / 0 / 0 |

paired episode 差は 0、95% paired percentile bootstrap は退化した [0,0]、
two-sided randomization p=1、MCID=.10。天井効果のため母集団の同等性・優位性・
意味差の排除を証明していません。pilot SD=0 では power を信頼して推定できず、
SD=1 の保守的 normal planning は N=785（80% power、alpha=.05）でした。
検証候補の観測最大は allocation 当たり 1 で、持続的 backlog は発生していません。

adaptive は generated token が 17 多く、active mean wall が 1.7289 秒長くなりました。
副指標の記述値であり、多重比較を補正した有意性・速度優位の主張ではありません。
shared CPU/cache、有限 synthetic family、一つの model、episode 内の相関が限界です。
C1/C2 の別入力への利用と C3 形成の lineage は確認しましたが、能力純増・自己加速・
collective intelligence phase の因果的実証ではありません。
ordinary receipt 870/arm は nested primitive/provider/calibration を含み、独立 tasks や
870 新能力を意味しません。stage 別 signed costs、C3 の post-hoc resource group は
[元解析](experiments/gemma-041/confirmation-v1/analysis.json) と
[resource table](experiments/gemma-041/confirmation-v1/resources.json) に残しています。
nested wall を加えて total とせず、欠測 currency をゼロにしていません。

## 7. 再計算と原記録

[実行・verify・analyze 手順](gemma-041.md)、[API](api.md)、[復旧](deployment.md) を参照。
公開用コピーは原署名、CAS、model request/response、source snapshot を維持し、
unsigned metadata の必要な path/DSN 変換だけを original/public hash 表で記録しました。
確認用 2,011 files の 2 files が加工対象です。原本・public copy の raw 検算が通っています。
大きい raw と CI 失敗・成功履歴を [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.1) に公開しました。
3 ZIP は計 11,568 original file copies、unsigned metadata 359 files の変換、failure omission 0。
全 manifest hash・ZIP CRC・path/privacy scan と、全 10 assets の実公開 download hash が一致します。
weights、private key、operator home configuration は含めていません。

```sh
uv sync --all-extras --frozen
uv run python scripts/analyze_gemma_tabular.py verify --run YOUR-RAW-DIR --output NEW-VERIFY-DIR
uv run python scripts/analyze_gemma_tabular.py analyze --run YOUR-RAW-DIR --output NEW-ANALYSIS-DIR
uv run python scripts/check_gemma_report.py
```

offline commands は推論を呼びません。Git の LF と Windows 原解析の CRLF の hash は
[manifest](experiments/gemma-041/confirmation-v1/manifest.json) で分け、数値内容は同じです。

## 8. 配布の実際の状態

候補 commit は `1fd790d6c777841c37a142f1f5a16a4d3ce6e6a5`。
新 hosted build は測定済み immutable pair と同じ SHA256 です。

```text
2455fcab88a1dc732372b9a5c7c0eb7d16d3661b6bbf76e853ab8d03d52a0fb9  collective_intelligence_overlay-0.4.1-py3-none-any.whl
0262c0b53c936b4e08173c2340539e86e101bff4f383f4fef2aa0ee8913f2a99  collective_intelligence_overlay-0.4.1.tar.gz
```

固定 [v0.4.1 tag](https://github.com/kadubon/collective-intelligence-overlay/tree/v0.4.1) は
`bda9e16faeb536b705fd0659e8ca3469941d9f1e`、annotated object は `5e8fd5525db52acaa0d93cea9845e3a232672ca9`。
実公開 engine は `91f9a802b50ef81e8cda77ceb89d12ee63e1f772`、[OIDC run](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36987219345) は成功。
元 validation code は変更のない tag から実行し、実 workflow engine の commit/tree/hash は別 provenance です。
[PyPI 0.4.1](https://pypi.org/project/collective-intelligence-overlay/0.4.1/) と
[Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.1) の両配布物は上の値に一致しました。
Windows 3 stable minor の clean no-cache/no-config PyPI install は各 unit 113、model SDK 1、
Ollama SDK 5、sdist 114 件で failure/error/skip 0。12 environments は公開 root を含む監査・license・SBOM を通過。
最初の 3.12 index 解決が新しい版を取得できない失敗も保持し、同条件の新規 v2 は通過しました。
別の通常 PyPI install は全 85 package files が wheel に一致し、実サービス 3 process demo は
ACCEPT / REQUALIFY / REJECT、heldout `117.00`。配布のための再 build・tag 移動・保護設定変更はありません。
歴史的 v0.4.0 tag・公開物・否定結果・失敗原本は変更していません。

## 9. 未実施・残存制約

宣言した監査・実験・配布の完了に必要な外部権限の待ちはありません。新 package の実外部監査、長期 0.4.1 soak、
複数独立組織、電源断保証、GPU/別 backend での Gemma 再評価、一般的集団知能相は未実施。
初回 v0.4.0 duplicate-soak と original Mac fault 応答の厳密な根本原因は未確定です。
local aged-source probe は後者と整合する条件を再現しましたが、失われた応答を補完しません。
公開物の frozen description は prepublication の履歴を含むため、公開後の正本は
main Docs/Release の実結果とし、説明更新のために配布 bytes や tag を置換しません。
