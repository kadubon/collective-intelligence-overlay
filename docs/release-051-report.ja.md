# CIO v0.5.1 最終報告（2026-10-05 JST）

**0.5.1の公開と、宣言した検証は完了した。native gate、annotated tag、公式OIDCによるPyPI公開、公開後の同一bytes取得・新環境smoke・4導入profile、GitHub Releaseの6 assets取得、単一software evidence archiveを確認した。初回失敗を保持し、その原因未確定と検証範囲の限界を以下に記録する。**

本報告は仕様第17節の10項目に対応する。[実結果](release-051-results.json)、[native結果](release-051-native-results.json)、[監査台帳](audit-051.md)と[単一evidence archive](https://github.com/kadubon/collective-intelligence-overlay/releases/download/v0.5.1/collective-intelligence-overlay-0.5.1-evidence.zip)を根拠とする。以下のtest scopeは重複するため合算しない。

## 1. 実際の基準commit/tag、候補・公開commit

監査基準はclean main `d39ac26a342dc0e040e2368e5e364f534c08328c`、公開済み0.5.0 tagのcommitは `1c7e3527dc48580f92e70f2a3752d54e970808d4`。既存tag・配布物・原ログ・研究archiveを変更していない。

追加pre-actuation修正は `958e1e781b590c8f5957d375e3b65194d6c473e9`。[PR #7](https://github.com/kadubon/collective-intelligence-overlay/pull/7) はmerge済み。Docs `5212d7bd5550275cf9b92a6a4a37de7b7e7752c9`、README `9fedfbbeccf93c39395e313abbe295616cf12b8e` を含むsource freezeは `77db860ad5cfb5c0fc67befd8c5a267916527979`、treeは `a08d7facea20827024e59e9348e772946d184e2a`。

公開commitは `7540ae5bd6150e95038d27b39b4f1c17ac808456`。これはnative証拠を加えたDocs-only descendantで、packaged source/tests/workflow/metadata/lock/READMEはfreezeから変更していない。annotated `v0.5.1` objectは `53f1e7bb47f6c5668bf029611e59554c0eb88477`、peeled commitは同じ `7540ae5bd6150e95038d27b39b4f1c17ac808456`。tagの移動、配布物の再build・置換はない。

旧候補 `eda15996c8451f06d88399d13d3ddb3cfe972b90` のrun `37200404588` は追加修正によりsuperseded。原本3482件と失敗を保持し、旧runのretry・tag・公開はしていない。新候補 [run37209296412](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37209296412) は2026-10-04 14:26:58 UTCに一度dispatchした。初回failureを保持し、同source・同pairで後述の限定再実行1回を経てattempt2の必須gateを採用した。

## 2. 監査範囲、指摘、修正、test、未検証

有限なリスクレビューと修正diffレビューを行い、最終レビューで実証されたpre-actuation問題を優先して訂正した。同じ保守チームによるレビューで、第三者監査ではない。原記録・署名・identity、owner/read-only境界、5観測、費用・時計・coverage・pagination、invocation/UNKNOWN/復旧、API/CLI/package/Docs/releaseを対象とした。

| ID・優先度 | 実証した問題と修正 | 根拠・未検証の境界 |
| --- | --- | --- |
| L051-01 / P2 | 同時刻・片側sequence欠測からgross順序を推定した。順序不明をnullに戻す | 初回失敗と有限回帰。全履歴順序の証明ではない |
| L051-02 / P2 | foreign caller/receiver/scope/policyの利用・費用を混入した。存在する座標で集計を限定する | 前後回帰。欠けたlegacy座標は補わない |
| L051-03 / P2 | nested purpose/validityのdefaultを観測済みreuse/expiryにした。欠測・unresolved/nullを保つ | 元DSSE bytesと前後回帰。missing request.purpose単独の初回失敗はない |
| L051-04 / P2 | 別callerの操作を重複扱いし、同一操作の矛盾receiptを隠した。`(resource_owner, caller, invocation_id)` と内容を照合する | 公開050の失敗・実DB identity。誤ったcaller oracleは保存して製品根拠から除外 |
| L051-05 / P2 | foreign owner/ID衝突/receipt座標不一致をhandoff根拠にした。元source順とexact refを対応させる | owner collision・scope回帰。手で並べ替えたviewへ保証を広げない |
| L051-06 / P2 | 重複targetをqualification後に拒否した。32件上限・集合を副作用前に検査する | unit初回失敗、実PG/OPA state不変のfixed-only回帰 |
| J051-01 / P2 | decode前depth上限がなく、duplicate key/非有限定数を受理した。有限preflightと曖昧入力拒否を加える | 初回失敗と回帰、正当UTF-8/16/32保持。一部はfixed-only |
| E051-01 / P2 | 公式A2A SDKの最初のyieldで戻りiterator/clientを閉じなかった。正常終了まで読み、全exitでcloseする | 初回5失敗→既存3件を含む8成功。null保持、複数nonstreaming結果拒否 |
| E051-02 / P2 | outer ACCEPT・dispatch後、inner REJECT/UNKNOWNでactuator未進入でもallowanceがheldになった。exact callのprivate proofと現行DB所有権で原子的にsettleする | frozen eda/公開050 primary2失敗、source119/local-v4 installed8/実PyPI installed8成功。一般denial/cancel/crashへ権限を広げない |
| D051-01 / P3 | SECURITYのsupport対象が0.1.xのままだった。0.5.xの保守方針へ訂正する | 静的Git差分のみ。架空のJUnit失敗やSLAはない |
| D051-02 / P3 | 全operation登録必須という説明がsubmit境界等へ過大だった。binding executionと既存同時要求上限を明記する | 静的Git/Config/sourceのみ。新quota機能や実測DoS耐性ではない |
| R051-01 / P2 | release selector/profileが0.5.0までだった。同じgateを0.5.1に適用する | 有限selector/profile回帰。実native/tag成功は別証拠 |

既存の単一台帳 `docs/audit-051.md` にcompact per-finding証拠を追記した。全12件の確認・修正commit、file/symbol、trust scope、exact NodeID、原/修正JUnit/hash、未検証は `audit-finding-evidence-appendix-v2.json` に対応する。原JSON SHA-256は `4d19a889b42f634b6ea1865e83970d72c11f47ec7305b078353906190aebc6c8`、compact版は `fb2b0e58b18efc84fdfca3c2853f5e15deffd95e2d4f0ea1d3dc61fcfa212ee1`。旧10件と誤ったcaller/property oracleの原失敗・訂正理由も保持する。公開archive内の `release-evidence/finite-audit/finding-evidence-mapping-v2.json` は原本・公開版とも上記4d19のhashで、compatibility manifestも原本・公開版とも6cd4のhashである。第9節にarchiveの取得hashを示す。

E051-02の新8件はprimary2、lost ownership3、rollback1、実child inner-proof1、explicit owner reobservation1。primary2以外の6件は安全境界のfixed-only回帰。focused17は新7＋補助10で、後追加の実child caseを含めない。指摘数・通過件数を安全性の尺度にしない。

## 3. refactorの理由・差分・変更しなかった領域

`ddb5994` ではmaterial/Store ingestionに重複したexact DSSE読取りとhistorical compromised-key判定を小さなprivate helperへ統合した。byte/depth preflight→署名確認→元JSON decode、原payload digest、欠測metadata、unsigned Decision、現在の権限を生成しない意味を保った。意図した観測bug修正 `aa68e32`、A2A修正 `8b3ce38`、二巡目訂正 `3e67606` と別commitにした。

公開050とrefactor前後の正常synthetic fixtureは、derivative `generated_at` の12明示pathだけを除き、canonical hash `138a0a9f81d403bb1acd8b6c5c5ae50571e56e41bf9466b7dc071dc05c5d389e` で一致した。原時計・ID・digestは除外していない。保存済み比較であり、新nativeの実行数に加えない。

`958e1e7` は実証されたE051-02の限定修正。actuator第一処理でentryを記録し、inner admission refusalのexact dispatch callbackだけにprivate proofを結び付ける。Executorはoriginal request/identity、同worker/fence、active unexpired lease、actual/receipt未保存を検査し、budget→invocation→leaseのlock順でonce-only release・fence・signed cancelled receiptを同一transactionへ保存する。原dispatch履歴を保持する。既存public `finish`、`_release`、`_releasable` のsourceは保持した。

source-hashed operation/factory、reference/starter、model/security/core storage、DB migration、研究driverを整理のために移動・整形していない。新runtime/DB/planner、一般化frameworkは導入していない。source digestはclosure・remote code・全依存環境の証明ではない。

## 4. API/CLI/schema/digest/署名/DB/依存の互換性

freezeで生成した `compatibility-boundary-v2.json` SHA-256は `6cd4b70077d281bb75ccb9d07697971d57cc945507e9270b98e917310edad5e4`。公開API19 signature（lifecycle8/runtime11）、packaged schema14、lifecycle class/enum23、runtime model/dataclass・SQL AST、migration22版＋env.py計23ファイルを比較した。公開signature/field/enum/import/wire/DB schema/migrationを維持する。5観測のschema version1・derivation version0.5.0はpackage version0.5.1と別である。

旧package97ファイル中90件byte一致、意図した変更7件（lifecycle3、a2a_service、bindings、invocations、steps）、新private `_lifecycle_json.py` 1件、削除0件。reference/starter12ファイル、登録operation/factory88 span、binding identity5 span、accounting3 spanのsourceを保持した。bindings/invocations/stepsのfile全体がbyte不変とは記さない。

誤集計/defaultによる欠測補完、receipt矛盾、handoff根拠、曖昧JSON、副作用後の入力拒否、証明されたpre-actuation reservationに意図したbug修正差分がある。CLI mode/exit codeの回帰と静的境界は、全入力・全競合の保証ではない。

runtime dependency/extrasの追加・更新は0件。parsed pyproject/uv.lockの差はroot versionのみ。`requires-python >=3.12`、Apache-2.0、LICENSE/NOTICEを保持した。最終native pairとactual PyPIのwheel/sdist bytesは第9節のhashで一致した。PyPIでその時に解決された推移依存版は実profile記録であり、将来の全resolutionを保証しない。

## 5. 環境、pass/fail/skip、未実施

有限なsource/installed回帰と公開後確認はWindows11 AMD64、CPython3.12.14で実施した。局所回帰はuv0.12.19、専用loopback PostgreSQL16.15/port55451、OPA1.21.0、必要範囲の公式A2A SDK1.1.5を用いた。実PG caseは新DBで、既存050サービスを転用していない。既存 `CIO_PG_TOOL_PREFIX=["wsl","--exec"]` を明示した。静的extractor Python3.13.5はnative runtimeと別である。以下は重複scopeで、総件数を算出しない。

| 保存済み有限回帰 | Pass | Fail | Error / skip | 解釈 |
| --- | ---: | ---: | --- | --- |
| Lifecycle / Store baseline | 43 / 10 | 0 / 0 | 0 / 0 | 修正前。Storeは実PG/OPA |
| 公開050 wheel・訂正済み従来bug回帰 | 43 | 24 | 0 / 0 | checkout外通常install、旧版の期待失敗 |
| JSON初回 | 1 | 5 | 0 / 0 | depth/duplicate key/nonfinite |
| A2A lifetime初回→修正 | 0→8 | 5→0 | 0 / 0 | 公式SDK ASGI、実model0 |
| release wiring baseline→初回→修正 | 55→55→74 | 0→19→0 | 0 / 0 | selector/profileのみ |
| Lifecycle/JSON/property修正後 / refactor後＋Store | 79 / 91 | 0 / 0 | 0 / 0 | 訂正oracle原本を保持 |
| 二巡目初回→修正 | 2→86 | 5→0 | 0 / 0 | 別expanded collision8成功 |
| 既存安全経路・専用実service | 8 | 0 | 0 / 0 | receiptless/遅延commit/barrier/A2A |
| E051-02 frozen eda初回v1 / 強化oracle v2 | 4 / 0 | 2 / 2 | 0 / 0 | outer ACCEPT、inner拒否、actuator0のprimary2 |
| E051-02 focused | 17 | 0 | 0 / 0 | 新7＋補助10、実child追加前 |
| 7 integration suite runtime v1 | 117 | 1 | 0 / 1 | child setup二重予算23505、WSL tool prefix不足skip。製品fixではない |
| child setup訂正後 | 1 | 0 | 0 / 0 | fixed-only、製品source変更なし |
| 7 integration suite runtime v2 | 119 | 0 | 0 / 0 | 同じ119 NodeID、全8新case、実PG/OPA |
| 公開050 installed primary2 | 0 | 2 | 0 / 0 | 実site-packages旧版の期待失敗 |
| local-dist-v4 installed新8 | 8 | 0 | 0 / 0 | checkout外fresh wheel[agents]、98package file一致、実PG/OPA |
| 新native初回quick | 440 | 0 | 0 / 0 | attempt1原JUnit |
| 新native初回Intel313 source | 968 | 1 | 0 / 0 | total969、installed未到達 |

runtime v2 XML SHA-256 `592dd5d71a2335001d271f3731779990c53d59f7b1d70e3e35abd124c1c292ae`、log `e8d9eb632a765d79b1080a16ebf4f067e361de9e1f5c9c4b5e4f0010c5769c69`、`119 passed in 581.70s`。公開050 primary2 XMLは `26332e59f71cea7ee3bc691d22658e1bac0349f11d61e397805aeb041a9043b8`、local installed8 XMLは `048f7acdec7deb2d809188e0233d84fbf287f922d7927c0c415218bffd11b6b9`。全原失敗・skipを保持した。

local-dist-v4 wheel `151e48893dd2f83e524bdd17708786d05e85ff4e68f30151d10b4c11ed44521a` / sdist `de8da906738cadd9aa3e7590e20f21c1f173dd460bfb04a9cd180f4ac7c12b41` は局所事前検証用。最終native pair・実PyPI051の証拠にしない。

最終nativeはLinux/Windows AMD64、Darwin AMD64/ARM64 × CPython3.12.14/3.13.15/3.14.7の12 profile。各profileのsource969、installed agents957、agents-model mock1、agents-ollama mock11、rebuilt-sdist513はpass、fail/error/skipはいずれも0。source/installedの必須fault19群・観測24labelと従来numerical boundsを保持して全必須gateを通過した。有限fault profileの `formal_soak_or_release_approval` はfalseで、長期production soakではない。mixed Pythonは3.12.14↔3.14.7両方向pass。4 cross readerは各228新署名checkを通過した。これらはprofile内外で重複する。

初回Intel313はmacOS15.7.9 x86_64、CPython3.13.15、PG17.11、OPA1.21.0、SDK1.1.5/AnyIO4.15.1/httpcore1.0.9/httpx0.28.1/uvicorn0.54.0。唯一のsource失敗は `tests/e2e/test_adaptive_documents.py::test_peer_selected_document_formation_restart_and_withdrawal[calibration vocabulary-50-static-run-False-False]`。verifier起動後のreadiness metrics probeで、A2A Agent Card GETのTCP接続待ちがouter `asyncio.timeout(25)` によりTimeoutErrorとなった。application invocation前で、installed phase未到達。新pre-actuation8件のsource成功はsuite全体の失敗を相殺しない。

child log/PID/port/DB startup stackが原artifactにないため原因は未確定。25秒outer/30秒単probeという構造だけでcontract違反・infra flake・製品原因なしとは断定しない。同sourceでの再実行成功も原因証明ではない。初回source XMLは `926b3d3f0fd6aecbcf9e653fa2d1553da0d0100b6d70dfa53d9adfab404d1443`、API原logは `fff597bc282e4f4392eed6fe6657482487570f6c8f7697ac1480d813fef874ef`。

旧eda runはnative11成功・Intel312依存転送timeout1失敗（製品試験到達前）として別にsuperseded保存した。新Intel313と同原因とは扱わず、旧成功数を加算しない。

公開後、repository外のfresh Python3.12.14環境でcache-disabled actual PyPI resolutionを確認した。wheelとcore/agentsのinstalled98 packagefilesはbyte一致し、core optional importは全core child command/testでblockedと確認した。

| 実PyPI公開後の独立scope | Pass | Fail / error / skip | 内容 |
| --- | ---: | --- | --- |
| core lifecycle/JSON/property | 92 | 0 / 0 / 0 | core profile。optional agent/model importなし |
| A2A lifetime | 8 | 0 / 0 / 0 | 公式SDK、モデル推論なし |
| lifecycle Store | 12 | 0 / 0 / 0 | 実PG/OPA、認可・state不変・assessment preflight |
| pre-actuation | 8 | 0 / 0 / 0 | exact新8 NodeID、実PG/OPA、package origin guard維持 |
| 読取り専用CLI | 4 command | 全command pass | inspect/contributions/growth/handoff。pytest件数に加算しない |
| actual-service tutorial | 1 scenario | pass | A ACCEPT、B REJECT、withdrawal後REJECT、rows2/total5.00、model0 |

smoke記録 SHA-256は `37c9e98726ace9ba7632ce08c11db41eab89b2520084b86a2127ff5d7ac698ed`。core/A2A/Store/pre-actuationのXMLは順に `7f193fbb6ee088a01aae1ff040516d26ab448da6b440444e31b4d6d7dacf0516`、`515dd7f8b74015fac71f0c13602949fff4e347e48ac9370e571d5a463c643f30`、`3d4605458449589c29da8862a6b1a709e16e402ea97be274fdc2101a94b4756d`、`2453ab11f8a4e5b7cdb3f16cc3b071ad15925ebeee9d8fe702c9624dd761806e`。

同じactual-index検証の4導入profileはWindows11 AMD64/CPython3.12.14の1patchである。coreをextraとは数えない。

| 導入profile | actual resolved audit依存数 | Test pass | Fail / error / skip |
| --- | ---: | --- | --- |
| core | 31 | このpackage profileのpytestなし。別core smoke92成功は上表 | 該当pytestなし |
| agents | 64 | unit512 | 0 / 0 / 0 |
| agents-model | 67 | mock1、actual sdistからrebuilt wheelのunit513 | 両scopeとも0 / 0 / 0 |
| agents-ollama | 66 | mock11 | 0 / 0 / 0 |

全4 profileの既知advisoryは記録時0、license inventoryとSBOM各4を保存・確認した。package JSON SHA-256は `b85e6cae6dfe121cd634bd69e47d472a35fd70296a3cdbe0094936aaa77c0425`。依存数は各actual resolutionの数で、全将来依存の安全証明ではない。model/ollamaはmockであり実model pull・実生成を行っていない。

最初のactual-index orchestrationはglobal Python3.13に既存開発tool `piplicenses` がなくlicense収集で停止した。完了profile0、pytest未到達、core install/依存auditのpartial原本を保持した。既存locked CPython3.12.14環境を使う1回の既知setup修正を別outputへ実施し、source/lock/testsを変更せず上表を完了した。これは製品pytest失敗を修正した証拠ではない。原failure record SHA-256は `24f1258eb0704c8967906d5a8106936faaefd38fecfd37e6a1d1126b5a80d3ef`。

## 6. read-only、費用・時計・coverage、UNKNOWN/復旧

offline inspectはfetch/tool/model/qualificationを起動せず、owner読取り/exportはquery前に認可を検査する。実Store12件はrecord・budget・held invocation/lease・Decision/admission・feed等の登録table不変を比較した。明示assessmentは既存qualificationに委譲し、duplicate/上限はその前に拒否する。

費用は原event位置、owner/category/unit/statusを分け、再送と別caller/operation・物理報告を区別する。null/unavailableと0、duration種別/alias、occurrence/local reception/expiry/derivationを混同しない。欠測・不明順序はnull/Residual、ownerのbounded pageはpartialのまま保持し、世界履歴completeや因果的成長・節約を補完しない。

E051-02はexact callのactuator未進入proofと同transactionの現行所有権が揃う場合だけonce-only reservation releaseを許す。signed cancelled receiptはoutcome UNKNOWN、検査費用はoverhead、原dispatch履歴を保持する。金銭返金・外部作用取消・品質PASSの証明ではない。

general/child/entered denial、cancelled await、late commit、crash、lost/expired lease、proof不成立にrelease権限を広げない。明示ownerのreobservation/new attemptも同じpositive proof predicateを用いる。DB管理者は既存trusted infrastructure境界内で、malicious administrator耐性を主張しない。原DSSE/FAIL/withdrawal/UNKNOWNや旧uncertain reservationを書き換えていない。

公開後tutorialのformation receiptを保持し、functional noveltyはunknown、viewのcurrent admissionはunassessed、authorityはnot_granted、coverageはpartialとした。deterministic result rows2/total5.00を集団知能の因果的成長と解釈しない。

## 7. 実生成0、新実験0、CIの節目と限定再実行

real LLM generation **0件**、model pull **0回**、新pilot/科学比較/benchmark/長時間soak **0回**。有限fault/property/mock/loopback service回帰は別である。credentialsやSDKの存在を実推論許可にしていない。

局所再現・lint/type/実service後にPR #6と旧eda集約nativeを用い、追加実証修正・DocsをPR #7へまとめ、新freezeの集約nativeを一度dispatchした。初回failure原本3790件のmanifest SHA-256は `744d9f1a7c32fe4e58cb44243e94bd10394db082ad19656f13549fdd54e64dae`、dispositionは `94b521ddb98c5648a49c75f7abce3a00c4db83d39030adc0f48638413fc73496`。native11成功・sole source失敗・package未到達・original job/artifact ID・pair・raw logを保持し、初回を除去していない。

明示的な人間承認記録に基づき、2026-10-04 **17:04:50.044071 UTC**にIntel313 job111457046859だけの再実行を1回要求した。対象1＋既存依存cross4＋ready1の実新job6件が成功した。全run rerun/cancel、debug追加、source/tests/workflow/pair変更、timeout増加、assert緩和は行っていない。承認の公開証拠は本文を除いた記録として保存した。

authorization SHA-256 `81a1f97072943ed942cbc611d7091992f2d06e5bee4ed6bcf4dd9d48251a075e`、plan `b4df34d5b2f1e6a1eb3a855a98c5daa348cd0d220afb30e2469fe9f3ea65bdfc`、action `1fcc571c6d3d7c932de30bb73068522616aaafe8b4b4fd6a54991eec94928a7d`、受理result `f78bab03745699f535aabb7f10e23f300268be231e8e9c6d5e8df95aa2599ccf`。この受理result単独はgate成功の証拠ではなく、完成したrun/collectorの結果で成功を確認した。先行helperのsingleton cross preflight denialはCI request前の停止として保存した。自動2回目はない。

初回成功14件（native11＋quick/candidate/mixed）はoriginal execution IDとlatest bookkeeping alias IDを分けて保持した。latest APIでは14件のID/run_attempt等が変化した一方、15 execution fields・249 steps・元timestamps・original artifact IDs/digests/bytesの対応を照合した。map SHA-256は `5f367598129bca1c38526f42f7bb7847839725fd4a1964aa4de10d908ad8382e`。「latest IDも同じ」「GitHub内部で絶対に再実行されなかった」とは主張しない。

canonical native原本3842件のmanifest SHA-256は `b83e89a46459c9243b2ca51015d32d56c71b41c6582d3b382a519d4f002c52d2`。原complete gateを変更せず、全12profile・mixed・cross4・fault必須条件と同一pairを検証してgate採用を完了した。gate JSON自体にはfailed-attempt/approval historyが含まれないため、別保存のprovenance/authorization/first-failure記録をarchive内で対応させた。authorizationの公開版hashは `f2b91401952562464aad42e29d1297a27a34a5ea3a7be091a80c9b309d48fac9` で、上記の原記録hashと区別する。再実行成功を初回原因の診断とは扱わない。

公開commitのmain push [quick37226417161](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37226417161) は成功。[tag workflow37226613301](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37226613301) attempt1も成功し、candidate/ready/publishが成功した。tag quickはSKIPPEDで、mainの別quick成功と区別する。tag時にnative matrixを反復しなかった。

## 8. 更新したREADME/Docs/AGENTS/SKILL、最短コマンド

英日README、Start/Tutorial/API/referenceでmodel-free入口、tool接続、5観測、外部サービス、trust/非保証を整理した。最新051 commandsはimmutable pairのREADMEにも含まれる。pre-actuationの狭いrelease条件、既存 `max_owner_requests=16` / `max_caller_requests=4` が同時要求上限で累積CPU/DB/storage quotaではない点を説明した。operator control guidanceは新機能ではない。

AGENTSの現行不変条件を先頭へ集約し、旧規則を `docs/agents-history-through-050.md` にbyte-exact保存（SHA-256 `dabac9a8a78ccff949ccc41669d7f33937470dd1fffac09cf72be71cd919a2a8`）。standard `.agents/skills/collective-intelligence-overlay/SKILL.md` と既存綴り `slills.md` の入口を整合させた。CONTRIBUTING/SECURITYはbug/security/互換性・有限修正を優先し、SLAや常時監視を約束しない。

repository外の新directoryから実行できるWindowsの最短入口は次である。actual-indexの051取得とoffline CLI成功は公開後に確認済み。

```powershell
uv venv .venv --python 3.12.14
. .venv/Scripts/Activate.ps1
uv pip install --no-cache --no-config --default-index https://pypi.org/simple collective-intelligence-overlay==0.5.1
collective-intelligence-overlay lifecycle inspect --fixture
```

fixtureは `current_admission: unassessed` / `execution_authority: not_granted` を示す。exit0はbounded resultでcurrent grant/品質PASSではない。offline fixtureにDBやmodelは不要。owner DB inspectionにはPostgreSQL、明示assessmentにはOPA、agent接続にはextrasが必要。4 read-only CLIとmodel-free actual-service tutorialは第5節の実証済みscopeである。

immutable tag/distributionに含まれるREADMEは公開前snapshotである。公開後mainの英日README/CHANGELOG/releasing/既存audit ledgerは実結果への状態説明とリンクを更新した。tagや配布bytesを変更せず、既存のCLI commands・旧release履歴・単一台帳構成を保った。

## 9. tag/Release、CI、PyPI、hash、公開後installの実状態

公開は既存 `.github/workflows/workflow.yml` / protected environment `pypi` / official Trusted Publishing OIDCを用いた。publisherは固定 `pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33`、frozen workflow SHA-256は `3c64d0f7beec77af6c0b3f61ea30241acecc1ef36aae516e650fb82d2fc21529`。long-term token、skip-existing、tag付替え、候補再build・既存配布物置換はない。

| 証拠 | 実際の状態 |
| --- | --- |
| native source / tree | `77db860ad5cfb5c0fc67befd8c5a267916527979` / `a08d7facea20827024e59e9348e772946d184e2a` |
| 最終native | run37209296412 attempt2 SUCCESS、12native・mixed・cross4と必須fault条件pass |
| complete gate SHA-256 | `0d5691a7507ada4cfa375e91ab70b2205b06e5b1370ef9008470dfc1b07cf4b6` |
| manifest / native results | `docs/release-051.json` SHA `938ea4b1e82e60db704615ef5e9e4dd681191178adacfe550bdadc36f92dbd9b`、`docs/release-051-native-results.json` SHA `fb97905cb2c112f7d177e39231cc6cd283eff6375207fc706d92ef6eef8d1d67` |
| publication commit | `7540ae5bd6150e95038d27b39b4f1c17ac808456` |
| annotated tag | `v0.5.1` object `53f1e7bb47f6c5668bf029611e59554c0eb88477`、peeled7540 |
| publication main quick | run37226417161 SUCCESS、同7540。tagのquickではない |
| OIDC tag run | run37226613301 attempt1 SUCCESS。candidate111507456673、ready111507512668、publish111507595631 SUCCESS。quick111507457635 SKIPPED |
| wheel | `collective_intelligence_overlay-0.5.1-py3-none-any.whl` / `35da08b11de4fa7bd35fb517055f60edf8dd8b866de7a1b4005dcbc07a3c29e9` |
| sdist | `collective_intelligence_overlay-0.5.1.tar.gz` / `86326198bb82a5c7ef0afc27a739cb1bc337a8cb93c89dd13a13fc7af3695703` |
| actual PyPI metadata/download | [PyPI051](https://pypi.org/project/collective-intelligence-overlay/0.5.1/)から実取得し上記pairとbyte一致。download record SHA `876e329ade54899caee622dcafdde479cd8758293ff5ba2b820892005b202d84` |
| fresh actual-index profiles | Windows AMD64/CPython3.12.14の1patch、core＋agents/agents-model/agents-ollama計4profile。tests・供給網確認は第5節 |
| actual-index機能確認 | checkout外core92/SDK8/Store12/pre-actuation8成功、CLI4、実service tutorial成功。重複scopeは非加算 |
| owned service終了 | 専用PG55451 stopped、data/logs保持、他service不変。cleanup record SHA `be8cd5d966b4d6cfdd6ee91149a526429c9d0258ff19b48bcd397b899fc99bed` |
| 公開証拠の変換 | release-evidence subset274 filesのうちunsigned metadata50件に対象変換。originalsとDSSE bytes不変。最終archive4073 membersの宣言hashを実downloadで照合 |
| single software archive | [evidence.zip](https://github.com/kadubon/collective-intelligence-overlay/releases/download/v0.5.1/collective-intelligence-overlay-0.5.1-evidence.zip)、4073 members、31969754 bytes、SHA-256 `e4b39b061a152cd165a18c5dbbc883bfcfaba0725afb8e1e7a27d0fed1cd4443`。実取得bytes・宣言member hashes一致、再圧縮なし |
| GitHub Release / six assets | [v0.5.1 Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.5.1)、release403172457、2026-10-04 19:24:57 UTC公開。wheel/sdist/evidence.zip/native gate/asset manifest/SHA256SUMSの6 assetsを実取得して原bytes・hash一致 |
| final results / evidence links | [release-051-results.json](release-051-results.json) は `published_and_declared_verification_complete`、SHA-256 `c8507a9c3a435528cccc7cb5d074f9733dc294ebf9eed9176ac8a728be1a2d5e`。archive内pathと原本・公開版hashを記録 |

tag action record SHA-256は `b57cbf7c948efcaab660a4b2050b6a6d99894d77bf58d04ed651fa44533d4105`。tag workflow wrapper SHA-256は `ed8278e8b184b9ad55e79dd50103bc8b42e188bfaf9e1ed81a5b7fec5ec1e865`。action時のhistorical pending statusは、後の実workflow/PyPI成功と区別する。tag時のheavy jobsはskippedで、native実績は認証済み候補runから再利用した。

公開archiveはoriginal/public derivativeのhashと変換を分けた。private-key、home-path、operational-DSNの対象scanを通過したが、完全なprivacy監査ではない。原署名DSSE bytesを保持した。既知public synthetic fixtureのexact test identityをhashで限定したscan例外は一般URIやoperator情報の公開許可ではない。旧研究raw/model weightsを再packしていない。初回source XMLは原本・公開版とも926b、初回job logは原本fff597・公開版 `416880138de7a24c4588735f048fed0c99d100ba29871da2f102215e2f208a6b` で、変換の対応をresultsに記録した。

## 10. 残るリスク、blocker、未監査範囲

新Intel313初回失敗原因は未確定で、product/test/infrastructureを識別するchild診断が欠ける。同sourceの限定再実行成功・必須gate採用でも欠測は解消しない。過去のDarwinIntel314 receiptless False-dispatch失敗も原因未確定（原log `d705391d29a38ebbbc8c850453b87ec7617e2bffe481b2eb8dde9feca2259ab2`）。Windows局所回帰や別sourceのMac成功を過去原因の修正証明にせず、新Intel313と同原因と推定しない。

frozen SDK modelのnested mappingはmutable、`model_copy(update=...)` はvalidationを迂回する。trusted hostが原projectionを改変しない前提を保持し、侵襲的model再設計はdeferred。未認証remote permission bypassが実証された指摘ではない。手で再構成・並べ替えたviewへ元source/Decision順のcorrelation保証を広げず、欠けたlegacy scope・cost対応・世界履歴を補完しない。

認証済み・許可済みpeerによる継続的inspectionはCPU/DB/storageを消費し得る。同時要求上限16/4はidentity単位の累積rate quotaではなく、新rate-limit serviceは追加していない。owner単位のDB直列化はcorrectnessを優先し、高負荷のthroughputは未測定である。callable digestはfunction sourceのidentityで、globals・依存module・環境変数・native library・runtime設定のattestationではない。host、DB管理者、installed code/checkers、OPA/policy、key registry、clockはtrusted computing baseに残り、外部penetration test、multi-organization key management、長期availabilityは未確立である。詳細は[security境界](security.md)と[設定](configuration.md)に記録した。

全入力・全競合、adversarial/high-load throughput、外部production、将来SDK/Python、第三者監査、長期運転を検証していない。owner-lock throughput/資源枯渇のseverityは未測定。完全安全・全bug除去・商用品質・因果的集団知能成長を保証しない。静置後はbug/security/明確な互換性問題・小さな使い勝手の有限修正を優先する。

宣言したnative/tag/PyPI/smoke/4profile/cleanupと、第9節のarchive・実GitHub Release6 assets取得・最終resultsを完了した。外部承認・接続の未解消blockerはない。承認済み単一retryは消費済みで、追加実行を予定しない。公開完了は初回失敗原因の解明や全環境・全入力の安全保証を意味しない。
