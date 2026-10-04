# Collective Intelligence Overlay

Collective Intelligence Overlayは、能力の原記録を保持して読むlifecycle layerです。
toolや手順の検証、受け手の判断、利用、費用、未解決事項を原記録へ結び付けます。
機能的新規性、因果寄与、知能成長を自動認定するものではありません。

例えば、他agentのCSV toolを使う前に、正確な版、別checkerが確認した条件、
誰の受入・不採用判断か、費用や副作用の不明点を確認します。
各参加者が自分のpolicy、鍵、予算を保持します。
**Evidence is shared; admission is local.**

[English](README.md) · [最初の手順](docs/start.md) ·
[Tutorial](docs/lifecycle-tutorial.md) · [API reference](docs/lifecycle-reference.md)

## インストールと必要なサービス

**この手順の対象は最新の安定化candidate、0.5.1です。**
観測identity、purpose・validity欠測、期間の座標、handoffの根拠、bounded JSON入力、
標準A2A clientの終了処理を修正します。有限レビューと互換性の範囲は
[監査台帳](docs/audit-051.md)に記録します。このsource時点ではnative gateと公開は未完了で、
以下のindex導入コマンドは0.5.1公開後に利用できます。正確なhashと実検証は
[release記録](docs/releasing.md)を確認してください。公開済0.5.0と旧版は
[archive](docs/research-archive.md)に保持します。

coreのrecord型・offline viewにはサービスやモデルの起動が不要です。
ownerのDB inspectionにはPostgreSQL、明示的な受入評価には加えてOPAを使います。
optional `[agents]`はMicrosoft Agent Framework（MAF）、A2A、MCPの接続です。
`[model]`／`[ollama]`は別のoptionalモデル接続で、credentialsの存在だけでは推論しません。

## First run from the installed package

repository外の新しいディレクトリから実行します。Linux／macOS:

```sh
uv venv .venv --python 3.12.14
source .venv/bin/activate
uv pip install --no-cache --no-config --default-index https://pypi.org/simple collective-intelligence-overlay==0.5.1
collective-intelligence-overlay lifecycle inspect --fixture
```

Windows PowerShell:

```powershell
uv venv .venv --python 3.12.14
. .venv/Scripts/Activate.ps1
uv pip install --no-cache --no-config --default-index https://pypi.org/simple collective-intelligence-overlay==0.5.1
collective-intelligence-overlay lifecycle inspect --fixture
```

同梱入力は**明示的synthetic fixture**です。PASS、異なるreceiverの判断、completed reuse、
費用欠測、withdrawalを別々に表示します。`current_admission: unassessed`、
`execution_authority: not_granted`で、DB・network・model・tool・policyを実行しません。
Residualは根拠付きの未解決事項です。自動で仕事や法的責任を割り当てません。

## 既存toolへの接続

<a id="register-your-application"></a>

[モデル不要のservice tutorial](docs/lifecycle-tutorial.md)で`[agents]`を導入し、
既存Registry／Executorへ信頼されたtoolを登録します。別checkerの検証とreceiverごとの
OPA判断、実利用、withdrawalを追います。専用PostgreSQLとOPAを使い、モデルは起動しません。
3別processのpeer構成や自分のapplicationへの追加は
[登録とnetwork設定](docs/quickstart.md)、[integrations](docs/integrations.md)へ進みます。

## 5つの観測

<a id="what-it-provides"></a>

| 型 | 示す内容 |
|---|---|
| `CapabilityLifecycleView` | 正確な候補、証拠、過去の判断、利用、費用、withdrawal |
| `ContributionObservation` | copy／import／reuse／formation input／new candidate。因果creditではない |
| `Residual` | 不足・不明・失効・不整合と原記録参照 |
| `GrowthObservation` | 独立したstockの両端、期間のservice観測、型付き費用 |
| `HandoffObservation` | proposed／received／assessedの材料。配送・実行許可ではない |

[SDK／CLI](docs/lifecycle-reference.md)は有限資料またはownerのbounded pageを読みます。
`inspect_lifecycle`／`observe_contributions`／`observe_growth`／`build_handoff`はread-onlyです。
明示的な`assess_stock`だけが既存qualificationへ委譲し、Decisionを保存します。
core lifecycleはagent／transport SDKをimportしません。実行は従来のMAF／A2A／MCP adapter等が
担当し、新しいscheduler、event store、中央managerは追加しません。

## 履歴・権限・データ

<a id="operate-and-assess"></a>

過去のPASS／ACCEPT、署名、completed receiptは、現在の受入・実行権限・業務品質とは別です。
実行は既存Executor gateを通します。UNKNOWN、不在、FAIL、未実施、期限切れを保持します。
entry数は宣言したrecord identityの集計で、意味上の能力数ではありません。

host、DB運営者、登録checkerを信頼する前提です。read権限はownerへ限定します。
参照URL／pathを自動fetchせず、明示的な原文exportは署名payload bytesを保持します。
view JSONは別digestです。秘密原文、鍵、logを保護してください。
pagination・expiry・削除で不確かな副作用を解決したことにはしません。
[概念](docs/lifecycle-concepts.md)、[security](SECURITY.md)、[deployment／recovery](docs/deployment.md)を参照します。

## 互換性と検証

Python >=3.12。Linux／Windows／macOS Intel／Apple Siliconの宣言profileは
[runtime matrix](docs/validation.md)にあります。公開済**0.5.0** pairに対してnative 12件、mixed Python、
cross reader 4件が通っています。実PyPI bytesとclean installの検査は
[実装register](docs/lifecycle-050-implementation.md)に記録します。
lifecycle層によるDB migrationやwire record変更はありません。
[移行](docs/migration-050.md)では旧binding・時計の欠落を説明します。

source検査は`uv sync --all-extras --frozen`、`uv run ruff check .`、`uv run mypy`、
`uv run pytest`、`uv run python scripts/check_docs.py`、`uv build`です。
service skipを構成の検証成功とは扱いません。licenseはApache-2.0で、
依存条件は[compatibility](docs/compatibility.md)にあります。

過去の負の結果と制約は[research archive](docs/research-archive.md)へ保持します。
CIO固有の蓄積利益は未実証です。今回の安定化releaseでは新しいmodel generation、
研究比較、benchmark、長時間soakを実施しません。
