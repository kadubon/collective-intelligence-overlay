# Collective Intelligence Overlay

**証拠は共有し、受入判断は各参加者が保持します。**

生成した結果、検証された結果、利用先に適合した能力を区別するPython製のoverlayです。
既存agentに追加し、能力候補・証拠・費用を交換します。各peerは自分の鍵、DB、
予算、受入ポリシーを保持し、他者の成果を拒否できます。

実行はMicrosoft Agent Framework（MAF）、通信はA2A、tool接続はMCPを利用します。
集団全体を管理するagentや独自workflow engineは必要ありません。

## できること

署名付きの能力・証拠を保存し、受け手・用途・環境版・権限・期限に基づいてOPAで
再利用を判定します。UNKNOWNや異論は消さず、既知の依存失効を実行前に検査します。
PostgreSQLで重複、費用、leaseと古いworkerの結果を管理します。

APIキー不要のデモでは、別プロセスの3 peerがCSV集計とHTMLレポートの能力を形成し、
別主体による検証、移転、合成利用、依存失効を一巡させます。
ローカルの別identityは、別組織や統計的独立性の証明ではありません。
署名、配送成功、schema一致だけで成果の正しさを認定するものでもありません。

## 最短の確認

Python 3.12、uv、PostgreSQL 16、OPAが必要です。有料モデルは不要です。
```sh
git clone https://github.com/kadubon/collective-intelligence-overlay.git
cd collective-intelligence-overlay
uv sync --all-extras --frozen
uv run python scripts/fetch_opa.py
```

専用の開発用PostgreSQLを準備し、`CIO_TEST_DATABASE_URL`と`CIO_OPA`を設定します。
OS別の手順は[quickstart](docs/quickstart.md)を参照してください。
```sh
uv run collective-intelligence-overlay demo --directory .local/demo
```

期待する結果は、受入`ACCEPT`、評価用CSVの合計`117.00`、環境版変更後`REQUALIFY`、
依存失効後`REJECT`です。実行後もDBとartifactを保持します。

## 既存agentへの追加

`Overlay.qualify(request)`で候補を調べ、`Overlay.execute(request, operation)`で
実行直前に再判定します。[MAF/MCP/A2A連携](docs/integrations.md)と
[API/CLI](docs/api.md)に具体例があります。model呼出しには明示的なopt-inが必要です。

DBとhostの管理者を信頼する構成です。[セキュリティ境界](docs/security.md)、
[運用・復旧](docs/deployment.md)、[検証状況](docs/validation.md)を確認してください。
長期運転、外部監査、複数組織運用、一般的な知能成長は実証していません。

テストは`uv run pytest`、buildは`uv build`です。サービス不足によるskipを成功扱いしません。
ライセンスはApache-2.0です。[依存版とライセンス](docs/compatibility.md)、
[研究との対応](docs/research-mapping.md)、[公開状況](docs/releasing.md)を参照してください。
