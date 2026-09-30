# Collective Intelligence Overlay

**証拠は共有し、受入判断は各参加者が保持します。**

生成した結果、検証された結果、利用先に適合した能力を区別するPython製のoverlayです。
既存agentに追加し、能力候補・証拠・費用を交換します。各peerは自分の鍵、DB、
予算、受入ポリシーを保持し、他者の成果を拒否できます。

実行はMicrosoft Agent Framework（MAF）、通信はA2A、tool接続はMCPを利用します。
集団全体を管理するagentや独自workflow engineは必要ありません。

**0.3.2のsource候補**では、ownerに限定した有限のinvocation整理と、Intel／Apple Silicon
Mac向けOPA導入を追加しています。旧workerをfenceし、未dispatchを正に確認できた予約だけを
解放します。dispatch済みの作用はUNKNOWN・予算拘束として残ります。
Macの公開ゲートは未完了で、下記の公開済み版は0.3.1です。
[native導入](docs/quickstart.md)、[cleanup API](docs/api.md)、[検証状況](docs/validation.md)を参照してください。

## できること

**0.3.1をPyPIへ公開しました。** 大量履歴でのowner・Subject完全一致のrevoke、
無効提案の個別隔離、期限切れ機会のownerによる明示的再観測、Registry・Executor・MAFを
通る論理A2A call IDと再送・照会の対応を修正しています。
[APIの例](docs/api.md)でrevoke、拒否category、`reobserve`、`call_id`・`call_scope`を、
[検証記録](docs/validation.md)で修正前後の実測を確認できます。必須の6環境すべてで
source 258件、installed agents 257件、model 1件、再build sdist 31件と
core import・CLI・resource検査が通過し、failure・error・skipは0件でした。
3.12.14・3.14.7の混在peerも両方向で通過しています。実PyPIから取得した配布物のhashは
検査済み候補と一致しています。公開後は3安定系列すべてでcacheを使わないPyPI導入を確認し、
最低版・最新版の全installed回帰も各257件、failure・error・skipなしで通過しました。
[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.3.1)へ
同一配布物と各runtimeの検証・依存報告を添付しました。

配布metadataは**Python >=3.12**で上限を設けません。Linux・Windowsの安定系列
3.12.14・3.13.15・3.14.7で検証済みです。将来のPythonまで検証済みという意味ではありません。
厳密な版・extras・OSの結果は[compatibility](docs/compatibility.md)に集約します。
`.python-version`は最低版での開発用pinです。別系列は
`uv sync --python 3.14.7 --all-extras --frozen`と`uv run --python 3.14.7 ...`で明示します。

0.3.0からは旧writerを停止し、backup後にmigration 0013/0014を適用します。
署名原文・旧remote ID・UNKNOWN・予約を保存し、新しい対応表が空でも未実行とは判断しません。
[移行・照合・復旧](docs/deployment.md)に従ってください。過去の負のpilot結果は保持しており、
このpatchで集団的能力形成の加速を証明したとは扱いません。

0.2.1 では、DB で未 dispatch と所有権を確認し、以後の dispatch を封じた
予約だけを一度だけ解放します。検査に使った費用は残り、実行可能性が残る予約と
旧履歴は保持します。[移行・復旧](docs/deployment.md)と[公開状態](docs/releasing.md)を
確認してください。

**0.3.0**では、ownerのgoal、署名付きの機会・peerの提案、局所的な
仕事選択を追加しています。hostが用途・導入済みbuilder・独立検証済みcheckerを
登録すると、観測に応じて形成・接続・検証を既存Executor上で有限に進めます。
証拠不足、checker不在、予算不足、実行結果不明は停止理由として保持します。
この追加機能を含む0.3.0のwheelとsdistを公開し、実PyPIからの導入も検証済みです。
[API](docs/api.md)、[外部アプリの登録例](examples/adaptive_documents.py)、
[実装と検証範囲](docs/implementation-status.md)を参照してください。

署名付きの能力・証拠を保存し、受け手・用途・環境版・権限・期限に基づいてOPAで
再利用を判定します。UNKNOWNや異論は消さず、既知の依存失効を実行前に検査します。
PostgreSQLで重複、費用、leaseと古いworkerの結果を管理します。

APIキー不要のデモでは、別プロセスの3 peerがCSV集計とHTMLレポートを登録し、
別主体による検証、A2A bindingの導入と再検証、合成利用、依存失効を一巡させます。
処理コードは移転せず、提供側の登録能力を呼び出します。
0.2.0では、登録binding、永続invocation、ページ同期・履歴、形成receiptを
追加しています。[外部の文書処理例](examples/document_application.py)では、3プロセスで
C3を合成・検証し、その出力からC4を形成して、再起動と元能力の撤回まで確認します。
[手順](docs/quickstart.md)と[検証範囲](docs/implementation-status.md)を参照してください。
実際の公開状況は[release記録](docs/releasing.md)に、0.1.0からの移行と復旧は
[deployment](docs/deployment.md)に記載しています。
ローカルの別identityは、別組織や統計的独立性の証明ではありません。
署名、配送成功、schema一致だけで成果の正しさを認定するものでもありません。

## 最短の確認

[PyPI 0.3.1](https://pypi.org/project/collective-intelligence-overlay/0.3.1/)を公開済みです。
有効化したPython >=3.12環境へ次のコマンドで導入できます。
配布物のハッシュ一致と公開後E2Eの結果は上記のrelease記録に記載しています。

```sh
uv pip install 'collective-intelligence-overlay[agents]==0.3.1'
collective-intelligence-overlay --version
```

デモと開発環境の再現には、以下のソース手順を使用します。

ソースはPython >=3.12、uv、PostgreSQL、OPAが必要です。有料モデルは不要です。
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

文書処理で静的方式と適応方式を比較する場合は、同じサービス設定と
新しい出力先を使います。

```sh
uv run python examples/evaluate_documents.py --directory .local/document-comparison --opa "$CIO_OPA" --seed 0
```

PowerShellでは`--opa "$env:CIO_OPA"`を指定します。有料モデルを呼ばず、
6つの分離された3-peer実験を実行します。記録済みの単回比較では、通常・入力接続
条件は両方式とも後続課題3件に合格し、検証資源不足では課題到達前に停止しました。
成果数とallowance消費の改善はなく、適応方式の実測時間は長くなりました。
[生データと限界](docs/evaluation.md)に、機能検証と効果の測定を分けて記載しています。

## 既存agentへの追加

hostがbinding、導入済み関数、入力評価器、実行contextを指定し、そのRegistryに
接続した永続Executorを使います。

```python
registry.register_local(binding, operation, assess)
invocation = await executor.invoke(
    "caller-stable-operation-id", binding.id, binding.digest, arguments, context
)
```

通常利用の前に対応する候補を公開し、独立した検証を受けます。実行時には実際の
入力と権限を再検査し、ownerの予算を予約して同じIDに結果を保存します。
実行完了は検証PASSではありません。[MAF/MCP/A2A連携](docs/integrations.md)と
[API/CLI](docs/api.md)に具体例があります。model呼出しには明示的なopt-inが必要です。

DBとhostの管理者を信頼する構成です。[セキュリティ境界](docs/security.md)、
[運用・復旧](docs/deployment.md)、[検証状況](docs/validation.md)を確認してください。
長期運転、外部監査、複数組織運用、一般的な知能成長は実証していません。

テストは`uv run pytest`、buildは`uv build`です。サービス不足によるskipを成功扱いしません。
ライセンスはApache-2.0です。[依存版とライセンス](docs/compatibility.md)、
[研究との対応](docs/research-mapping.md)、[公開状況](docs/releasing.md)を参照してください。
