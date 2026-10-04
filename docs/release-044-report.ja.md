v0.4.4 公開・検証結果

科学的状態は `assay_not_ready`、ソフトウェアは公開・宣言した検証が完了しています。
[機械可読記録](release-044-results.json)、[全 study 結果](studies/bounded-scratch-044/results-v1/report.ja.md)、
[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.4)、[PyPI](https://pypi.org/project/collective-intelligence-overlay/0.4.4/)。

1. 旧失敗：53件を不可視参照/schema12、入力・出力契約19、SQL実行2、意味不一致20へ分けました。
   係数不一致23件は重なる二次分類です。SQL例は incomplete input で、予約 alias が原因とは認定していません。
   二重集計の実行も確認できていません。旧検証済み派生物と exact-download proof を再利用し、旧推論・採点・raw を変更していません。

2. 自由度：SQL/formation とも L0/L1/L2 の1–3個の意味 enum、機能的候補2/4/8個を固定しました。
   SQLの負数/null/最新行、formationの非可換順序/net・gross mapping/scaleをモデルが選びます。
   hostは公開契約からSQL quoting/alias/binding、公開係数・固定 reducerを設定し、hidden oracleから答えを補完しません。
   任意SQL・架空skill ID・未知係数の自由生成は受け付けません。製品core86ファイルはstudyの公開済み0.4.2と同一です。

3. G0–G3：実smoke4/4、実観測schema4/6、全6 schemaのSDK直列化は synthetic 応答で確認しました。
   訪問した設定の候補24/24は実行・独立採点が一致（意味品質PASS4/FAIL20）、reference36/36、通信/schema/実行36/36です。
   G1はSQL L1=8/8、L2=8/8、formation L1=6/8、L2=7/8。二項95%記述区間は順に
   [0.631,1]、[0.631,1]、[0.349,0.968]、[0.473,0.997]で、適応的選定と小Nの限界があります。
   各96 seedのrandomは25/10/23/14、best constantは26/17/27/15、公開文規則は全て96/96です。
   L0は未訪問。G2は設定未選定・offered0です。G3-v3のM/C×family4経路は独立qualification、provider停止、
   receiver再起動・同じartifact/bindingの再構成後に成立しました。Full4/4は追加推論0、Empty4/4は検索stock0・各推論1です。

4. 比較開始：G1が両familyで事前規則上の天井に達したため、G2とconfirmationは開始していません。
   Full−Empty/C−Mの主比較、H_ACC/H_CIO/H_FORMは未推定です。G3で同じ元候補をM/Cに渡した到達性診断を効果比較へ足しません。

5. 品質・費用・stock：全44 offered行を[paired.csv](studies/bounded-scratch-044/results-v1/paired.csv)に保存しました。
   G3の8診断の品質・初回独立PASSまでのtime/tokensも全行掲載しています。元の実Gemma候補は2個、別owner履歴への複製は4です。
   各armの独自学習からのconfirmation stockは未観測です。失敗のT=300秒/B=4352 tokensは評価penaltyで、実消費とは別です。
   setup/import/検査/再起動/cleanupとnested RPCを保持し、親inclusive wallに二重加算しません。一部起動の固定wall小計は識別不能です。

6. 結論：有限手順の保存・移転・再構成は成立しましたが、scratch中間帯の感度は未確立です。
   蓄積利益、CIO追加価値、形成加速、chance優勢、無効性、同等性はどれも確立していません。非学習規則100%も保持しました。
   F/s、将来保守・energy・全computeは未推定・欠測です。算法発明や一般的知能の増大とは呼びません。

7. 実行・停止・CI：40実推論、実測/計上とも28178 tokens、usage欠測0、同時推論1。
   driver inclusive charge2953.683秒、修正待ちを含むsetup→停止確認の保守的charge3325.186秒です。
   256要求/400000 tokens/14400秒の実験上限を変更せず、所有model/observer/PGを停止しデータ・logを保持しました。
   元G3のhome衝突、G3-v2の別入力への実行ID再使用拒否、旧reader・新readerの失敗と修正履歴は保持しました。
   early quickは7 run（PR6/main merge1、失敗2を含む）、最終full dispatchは1回です。
   release selector文書pushのquickも1回通過しました。公開後の最終文書commitのquick結果はdelivery時に別確認します。
   Mac Intel3.12のGo取得timeoutはテスト開始前のインフラ障害で、元ログ/10診断を保持し対象jobと依存jobのみ再実行しました。
   最終12 native・mixed Python・4 cross reader・readyを通過し、tagでnative workloadを重複していません。

8. test・公開：lint/format/type、143対象unit、clean local core/CLI・agents396・mock model1・Ollama11・sdist397が通過。
   native各profileのsource/installed/sdist/service/security/license/SBOM結果は機械記録にあり、必須skipは0です。
   tag v0.4.4はcommit `5425daa397d8f4876d094ed1c5aea08008bb69cb`、object `c8c30338a1c075c1700772d3e42209be79d4a70c`です。
   [full run 37163191811](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37163191811)、
   [OIDC run 37175366587](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37175366587)が通過。同じwheel/sdistをpypi環境から公開し、再build・tag移動はありません。
   実PyPI bytesを照合し、Python3.12.14の新規no-cache/no-config通常installで86ファイル・CLI・6追加importを確認しました。
   実PG/OPA/MCP/A2A/MAF三プロセスdemoはACCEPT・117.00、環境変更後REQUALIFY、撤回後REJECTを確認。所有PG/子processは停止済みです。
   Releaseの8資産を再取得してbytes/sizeを照合し、40181196 bytesの単一ZIPの5553 membersを検査しました。
   SHA256 `2c0cec425616adec29adc5c28731c202c7402c91fb874a6b6e9ed102066b7aff`。全3 raw revisionのネットワーク遮断・推論なしの再解析は公開結果と一致しています。
   旧rawの再梱包・weights公開はありません。対象privacy検査は完全な外部監査ではなく、hashは同一性を示し真実性を自動保証しません。

導入: `uv pip install --index-url https://pypi.org/simple 'collective-intelligence-overlay[agents,model,ollama]==0.4.4'`。
開発: `uv sync --all-extras --frozen`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`、`uv run pytest`、`uv build`。
service testには実PostgreSQL/OPAの設定が必要です。source-only study/オフライン再検査の手順と依存は[methods](bounded-scratch-044.md)を参照してください。
