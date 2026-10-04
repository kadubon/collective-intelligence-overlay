# CIO v0.5.0 最終報告

2026-10-04。v0.5.0の実装、回帰、文書、同一配布物のOIDC公開、実PyPI install、
GitHub Releaseの全asset取得検査を完了しました。
[機械可読結果](release-050-results.json)、[native結果](release-050-native-results.json)、
[要件対応・失敗履歴](lifecycle-050-implementation.md)が検査範囲を記録します。

## 1. v0.4.4の確認範囲と新規推論

公開済0.4.4 archiveのbytesを照合し、3つの原raw revisionを、それぞれ凍結された
既存offline readerで一度ずつ検算しました。networkを遮断し、生成せずに公開済
analysis objectとの完全一致を確認しました。旧raw・reader・protocolは変更していません。

SQL L1/L2は8/8・8/8、compositionは6/8・7/8、公開文の非学習ルールは各水準96/96です。
G2とconfirmationは未実施、`assay_not_ready`を保持します。2つの実Gemma候補を
4履歴へ複製した8件の移転・再起動診断は、4つの機能的新能力や独立confirmationを
示しません。旧生成40件、measured/charged tokens 28,178、usage欠測0も一致しました。
今回の**新規real model generation requestsは0件**です。model pull、pilot、比較、
探索、benchmark、長時間soakを実施していません。CIO固有の蓄積利益は未推定です。

## 2. 5機能、API／CLI、既存責務の再利用

| 型 | 実API／CLI | 観測範囲 |
|---|---|---|
| CapabilityLifecycleView | `inspect_lifecycle`／`lifecycle inspect` | 候補、証拠、receiver判断、利用、費用、撤回 |
| ContributionObservation | `observe_contributions`／`lifecycle contributions` | COPY・IMPORT・REUSE・FORMATION_INPUT・NEW_CANDIDATEを別軸で保持 |
| Residual | 各reportに含む型付き値 | 不明・不足・失効・不整合を原参照とcoverage付きで保持 |
| GrowthObservation | `observe_growth`／`lifecycle growth` | 固定receiver／scope／policy／universeの独立した両端snapshot、期間履歴、費用 |
| HandoffObservation | `build_handoff`／`lifecycle handoff` | 根拠付きproposed／received／assessed、費用・Residual参照 |

`read_lifecycle_page`は既存Storeのbounded pageを読み、`export_originals`はownerが
明示したexact参照だけをexportします。read/exportはDecision追加、tool/model実行、
qualification、budget変更を行いません。明示的な`assess_stock`／`lifecycle assess`
だけが既存`capability_metrics`／`Overlay.qualify`へ委譲し、Decision等を書きます。
Store／Registry／Executor／OPA／FormationSession／既存MAF・A2A・MCP adapterの
権限・実行・保存責務は一つずつ維持し、第二のruntime・会計系を追加していません。

## 3. 正本、projection、新能力を自動認定しない理由

正本は既存記録と元DSSE payload bytesです。旧unsigned Decisionはunsignedのままです。
新viewはschema version 1／derivation version 0.5.0のread projectionで、元payloadとは
別digestを持ち、旧Record unionやfeedへ入りません。元にない時計はnull、legacy decoderが
補ったtop-level fieldは`decoder_default_fields`へ表示します。原文exportは元bytesを保持します。

異なるID／digestはrecord identityの差であり、機能的新規性や独立した起源の証明では
ありません。コピー、import、形成入力、実invocationの利用を分け、entry数・service・
token・通貨・durationを混ぜません。gross churnは完全な一致履歴がある場合だけです。
未知の因果・cost対応・単位を補完せず、inclusive durationを加算・換算しません。

## 4. 新旧互換とmigration

今回のDB migrationは不要です。基準commitから以前のpackage 85ファイルはbyte一致で、
以前から存在するファイルの変更は薄いCLI dispatcherだけです。既存wire schema、migration、
runtime実装は不変です。static比較に加え、全nativeで署名・旧API・実行・回復等の回帰が通っています。

原bytes、DSSE、invocation／remote identity、UNKNOWN、held予約、撤回、異論を保持します。
view、空Residual、署名、過去のPASS／ACCEPT、receipt完了から現在の実行許可を作りません。
旧版からの既存offline upgrade要件は[移行文書](migration-050.md)と[deployment](deployment.md)
のままです。未知の古いbinding・clock・完全履歴を歴史的事実として再構成しません。

## 5. pass／fail／skip／未実施と配布物の検査

最終native run [37186786810](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37186786810)
はLinux amd64、Windows amd64、macOS Intel、Apple Siliconの各
CPython 3.12.14／3.13.15／3.14.7、計12 profileで成功しました。

| 各native profileのscope | Pass | Fail／error／skip |
|---|---:|---|
| source full | 886 | 0／0／0 |
| installed agents full | 874 | 0／0／0 |
| model SDK mock | 1 | 0／0／0 |
| Ollama SDK mocks | 11 | 0／0／0 |
| rebuilt sdist | 445 | 0／0／0 |

core import／CLI／resources、実service tutorial、mixed Python、cross reader 4件も成功です。
sourceとinstalledのshort fault protocolは、既存19 required groups、3 owners、120–600秒の
数値条件を変更せず通っています。24 observed labelsは19 groupsと同義ではありません。
これは通常のsoftware fault回帰で、formal production soak承認ではありません。

公開後のWindows 3 patchで通常のcache無効PyPI installを行い、各444 agents unit、
1 model mock、11 Ollama mocks、445 rebuilt-sdistをpass、fail／error／skip 0と確認しました。
core含む12環境のpublished root込みadvisory／license／SBOMはfinding／audit skip 0です。
別のfresh coreは43 pass／0 fail／0 skip、97 package files byte一致、optional SDK import遮断、
4 JSON CLI modeを確認しました。optional pytest plugin未導入による`asyncio_mode`の設定warning
1件を保持します。実PostgreSQL／OPA tutorialもA ACCEPT、B REJECT、2 rows／`5.00`、
formationリンク、joules欠測、撤回後REJECTを確認しました。

途中の欠陥candidate、fixture失敗、旧Mac Intel／3.14.7のreceiptless回復失敗は消していません。
後者の原因は未確定です。最終nativeでは同caseを含む4caseが通りましたが、旧失敗原因の
説明にはしません。2つの失敗candidate runは明示承認を得て未完了jobだけ停止し、完了結果・
原log ZIP・配布物・reportを保持しました。0.4.x runには触れていません。
実モデル接続、新研究比較、長時間soak、外部production auditは未実施です。

## 6. READMEからの最小例とDocsの入口

[README日本語](../README.ja.md)と[English](../README.md)の導入版・commandは一致しています。
fresh directoryでPython 3.12.14のvenvを作成・activateした後、次を実行します。

```console
uv pip install --no-cache --no-config --default-index https://pypi.org/simple collective-intelligence-overlay==0.5.0
collective-intelligence-overlay lifecycle inspect --fixture
```

明示的synthetic fixtureで、DB／network／model／toolを起動しません。
`current_admission: unassessed`／`execution_authority: not_granted`とResidualを読みます。
[Start](start.md)から[実service tutorial](lifecycle-tutorial.md)、[Concepts](lifecycle-concepts.md)、
[API／CLI／how-to](lifecycle-reference.md)へ進めます。DB inspectionはPostgreSQLを使い、
明示qualificationは加えてOPAを使います。旧URL／anchor、運用・研究archive入口は保持しました。

## 7. 依存とlicense

runtime依存の追加・更新は0件です。pyprojectの変更はroot versionとdescription、
parsed uv.lockの変更はroot versionだけです。Python >=3.12、Apache-2.0、LICENSE／NOTICE、
上流表示を保持しました。optional agents／model／ollamaは従来の分離を維持します。
Gemma weightsの取得・再配布・license再分類はしていません。

## 8. GitHub、PyPI、hash、公開後installの実際の状態

sourceは`e830a6a54a22ba8190a64e0b184d461103287ee3`、release commitは
`1c7e3527dc48580f92e70f2a3752d54e970808d4`、immutable annotated tagは`v0.5.0`です。
[tag run 37194242517](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37194242517)
のcandidate／ready／publishが成功し、既存workflow.yml／Environment pypi／OIDCだけで
同一pairを一度公開しました。tag時の再build・native workload再実行・skip-existingはありません。

| 対象 | SHA-256 |
|---|---|
| Wheel | `ffa714868281925c500803cbf6762bb130c28e832ab68c70c8aa0f38e917690e` |
| Sdist | `916b0d16440b7888341a59ca452eb587030964da6d8de56f61cd59d8ff0ce752` |
| Software evidence ZIP | `af414d0b9920aea64da59609f986c6001361a6cbde143313e9cb297762a5763c` |

[PyPI 0.5.0](https://pypi.org/project/collective-intelligence-overlay/0.5.0/)のmetadataと実download、
通常installが一致します。[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.5.0)
の全6assetも実downloadしてbytes／size／hash一致を確認しました。ZIPは30,956,543 bytes、
3,864 member全hash一致です。旧scientific rawを再packせず、ソフトウェア検証だけを含めます。
原gateと公開metadata derivativeのhashを分け、署名付きenvelopeは編集していません。
tag／pair／gate／archiveを変えず、mainのREADME／Docsだけを公開後情報へ更新しました。

## 9. 未検証・残る制約と外部操作

必要な公開承認・接続待ちは残っていません。自分で起動したmarker付きtutorial PostgreSQL
だけを停止し、private key・原record・データ・logは保持しました。他サービスを変更していません。

公開後のactual-index installはWindowsの3 patchです。他OSの同じpublished bytesに対する
native gateは通っていますが、actual-index full native matrixは再実行していません。
完全な世界履歴、atomic cross-owner snapshot、rolling mixed-version deployment、一般的な
機能的新規性・因果credit・知能成長・CIO優位を保証しません。PEM／home／operational DSNの
公開前targeted scanは、完全な外部privacy／security auditではありません。
