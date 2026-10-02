# Collective Intelligence Overlay

agent同士で、証拠と利用条件を付けてtoolや手順を共有するPython packageです。
例えば、あるagentが文書workflowを提供し、別のcheckerが検査します。受け手は、
その版が自分のデータと権限に合うか判断します。各参加者は自分の鍵・DB・policy・
予算を保持します。**証拠は共有し、受入判断は各参加者が保持します。**

既存のMicrosoft Agent Framework（MAF）、A2A、MCP連携に、利用適合性の判定と
永続的な操作記録を追加します。実行とworkflow合成は既存SDKが担い、各ownerが
自分の仕事を選びます。集団全体のmanagerは必須ではありません。
hostとDBの管理者を信頼する構成です。

[English](README.md) · [Tutorial](docs/quickstart.md) · [API・CLI](docs/api.md)

この手順は**0.4.1**を対象にしています。実際の公開状態、candidateのhash、検証状況は
[公開記録](docs/releasing.md)、測定範囲は[0.4.1監査・Gemma実験](docs/gemma-041.md)
で確認してください。[0.4.0本番profile](docs/production-040.md)は過去の証拠として保持します。
0.4.1は[PyPI](https://pypi.org/project/collective-intelligence-overlay/0.4.1/)公開済みです。
[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.1)に実験・失敗・native検証の原記録とchecksumがあります。
固定30 paired episodesでは両条件ともheldout 180/180、主差B−Aは天井で0でした。
適応方式の優位や同等性は確認できていません。[9項目報告](docs/release-041-report.ja.md)を参照してください。

未公開の0.4.2ではreceiptのないUNKNOWNの回復と、別の[縦断実験](docs/accumulation-042.ja.md)
を追加しています。[監査状況](docs/audit-042.md)で、実smoke、決定的control、実行中の校正と、
未実施の確認・公開を区別します。現時点の検査は、蓄積やCIOの優位を示すものではありません。

## 提供する機能

- 版付きの能力と、独立した主体が発行するPASS・FAIL・UNKNOWNの証拠。
- 正確なbinding、実際の入力、環境、権限、証拠の鮮度、既知の撤回を確認するOPA判定。
- ownerごとのPostgreSQL記録、有限のallowance、fence付きlease、安定したinvocation ID。
- 登録したlocal関数、MAF workflow、MCP tool、A2A service。受信コードをimportしません。
- 既存executorを通じた有限の探索・提案選択・形成・検証。
- 配布済みfactory、readiness・drain、元IDでの照合、
  一貫したbackup、受付を閉じたrestore、scope付きの変更trial。

生成済み、検証済み、再利用可能は別状態です。署名は発行主体を示し、remoteの完了は
操作の状態を示します。どちらも業務結果の真実性を認定しません。証拠不足と外部作用の
不確実性はUNKNOWNとして保持します。[意味論](docs/semantics.md)と[security](docs/security.md)
に、アプリケーションの範囲、インフラ信頼、remote情報の鮮度を記載しています。

## install済みpackageでの初回実行

Python **>=3.12**と[uv](https://docs.astral.sh/uv/)を使います。0.4.1候補の実測対象は
CPython 3.12.14・3.13.15・3.14.7と、Linux x86_64、Windows x86_64、native macOS Intel・arm64
です。将来のinterpreterまで検証したという意味ではありません。
新しいdirectoryで、Linux・macOSでは次を実行します。

```sh
uv venv --python 3.12.14 .venv
. .venv/bin/activate
uv pip install 'collective-intelligence-overlay[agents]==0.4.1'
collective-intelligence-overlay --version
collective-intelligence-overlay opa-install --target ./bin/opa
```

Windows PowerShellでは次を実行します。

```powershell
uv venv --python 3.12.14 .venv
. .venv/Scripts/Activate.ps1
uv pip install 'collective-intelligence-overlay[agents]==0.4.1'
collective-intelligence-overlay --version
collective-intelligence-overlay opa-install --target ./bin/opa.exe
```

reference demoには、専用の開発用PostgreSQL clusterと、試験DB・roleを作成できるoperator
も必要です。[OS別native導入](docs/quickstart.md)に従ってください。Docker Desktopは不要です。
そのURLを`CIO_TEST_DATABASE_URL`へ設定して、次を実行します。

```sh
collective-intelligence-overlay demo --directory ./demo-run --opa ./bin/opa
```

Windowsでは`--opa ./bin/opa.exe`を使います。checkoutとmodel keyは不要です。
期待する値は`processes: 3`、`admission: ACCEPT`、report合計`117.00`、
`changed_environment: REQUALIFY`、`after_dependency_revocation: REJECT`です。
child processは停止し、秘密鍵・DB・artifactを保持します。再実行には新しい出力先を
使います。demoの認証とDB設定は開発用です。[本番deployment](docs/deployment.md)では
restricted roleとHTTPSを使います。

coreはrecord・policy・CLI、`agents` extraはMAF・MCP・A2A連携、`model` extraは
任意の実model例を提供します。有料推論は標準でOFFで、明示的なopt-inが必要です。
PostgreSQLとOPAは外部要件です。install・importでservice起動やbinary downloadをしません。

`ollama` extraは公開MAFのlocal Ollama clientを追加します。明示したloopback serverを使い、
weightsのpullやcloudへのfallbackは行いません。[実験手順](docs/gemma-041.md)にはclean installからの
実行と、推論を呼ばない`verify`・`analyze`を記載しています。別の5組pilotと固定30組評価は
ともに天井で、適応方式の品質上の優位を示しません。exact `gemma4:e4b`を準備し、専用の
cloud-disabled Ollama loopback serverを使います。測定したCPU Q4_K_M構成はcontext 4096、
推論並列1、runnerの観測peak working set約8.51 GBです。CIOはweightsをdownloadしません。

## 自分のアプリケーションを登録する

wheelには、完全なlocal登録例があります。
installした後、starterの雛形を生成します。

```sh
collective-intelligence-overlay starter --directory ./my-application
```

生成した`application.py`には、schema、callerの許可、Registry登録、candidate公開が
含まれます。配布済みの同等factoryは
`collective_intelligence_overlay.starter.application:configure`です。
自分のレビュー済み・install済みpackageで変更し、owner設定でfactoryを明示的に選びます。
この完全な例のtool本体は次の関数です。

```python
async def count_words(arguments: dict) -> dict:
    return {"words": len(arguments["text"].split())}
```

登録で独立したPASSは作りません。用途に合うcheckerを登録し、通常利用の前にscope付き
証拠を取得します。[連携](docs/integrations.md)にはRegistry・ExecutorとMAF・MCP・A2Aの
完全な接続例、[API](docs/api.md)にはfactory設定と永続的なcall IDを記載しています。

配布済みの文書referenceは3 peerを接続し、代替案探索、MAF report形成、独立検証、
reportを再利用したclassifier形成、受け手による利用適合性判定を行います。
既知の撤回後は、有効な新しい証拠と受入が成立するまで後続利用を止めます。
正しさはアプリケーションの契約で判断し、coreをこの業務例に限定しません。

## 運用と評価

初期profileは3つのpermissioned owner、ownerごとの単一service processとrestricted DB role、
設定済みHTTPS peer、導入済みtool、有料推論OFFです。HA、同一ownerの複数active writer、
外部exactly-once、普遍的SLAの主張は範囲外です。

[設定](docs/configuration.md)、[deployment・復旧](docs/deployment.md)、
[troubleshooting](docs/troubleshooting.md)に従ってください。candidateの`drain`は新しい作用を
止め、元の結果照会を続けます。restore後は検証、source全体の同期、業務固有の照合、
ownerの明示的resumeまで受付を閉じます。照合は保存したprovider IDを照会する操作であり、
再送や自動返金は行いません。

[検証](docs/validation.md)にはnative検査と失敗、[soak](docs/production-soak.md)にはすべての
要求結果があります。[比較実験](docs/production-experiments.md)では、独立したpair、負の結果、
異なる資源単位を区別します。一般的な適応方式の優位や知能成長は証明していません。

source開発ではrepositoryをcloneし、`uv sync --all-extras --frozen`を実行して
[contributing](CONTRIBUTING.md)に従います。必須service不足によるskipはrelease検証の成功と
扱いません。

新規コードはApache-2.0です。[LICENSE](LICENSE)、[NOTICE](NOTICE)、
[互換性・license](docs/compatibility.md)、[研究との対応](docs/research-mapping.md)、
[公開・移行履歴](docs/releasing.md)を参照してください。
