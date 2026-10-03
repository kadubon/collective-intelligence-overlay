v0.4.3公開・検証結果（2026-10-04 JST）

科学的状態はpilot-only / assay_not_readyです。confirmationは未実施です。
[実際の機械可読記録](release-043-results.json)、[英日study report](near-transfer-043.md)、
[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.3)、
[PyPI 0.4.3](https://pypi.org/project/collective-intelligence-overlay/0.4.3/)を公開しました。

1. 旧study：公開済み0.4.2 rawのverify/analyzeを各一回再実行し、結果は公開記録と一致しました。
   E/M/Cは181/244/244 calls、計669 callsです。実測805,556 tokens、charge815,796 tokens。
   Mのusage欠測1件は10,240-token予約を保持し、実消費や節約へ置換していません。
   空stockのE Full/Empty六対応では課題・初期seed・options・prompt・実request bytesが一致しました。
   確率的応答の相違から欠陥は認定しません。旧raw・tag・解析結果は書換えていません。
   新readerのAPI戻り値数・不正SQL例外の修正は別の履歴で、原sourceと失敗を保存しました。
   hashは同一性を示し、悪意ある操作者への耐性や物理的推論の真実性を無条件には証明しません。

2. 新protocol：`cio-043-near-transfer-cost-pilot-v1`、事前登録commit
   `4f1403dfe1b5da022a8378ceb032c25faa950cd5`、登録時刻2026-10-03 16:52:56.923021 UTC
   （10月4日01:52:56 JST）。推論時106 source filesを固定しました。実験runtimeは非editableの
   公開済み0.4.2 wheelです。Gemma4:e4bは7.5B Q4_K_M、digest
   `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`で旧studyと一致。
   Ollama0.35.0、CPU、context4096、num_predict1024、temperature .2、top_p .95、top_k64、
   think=false、draft predictionなし、同時推論1を固定しました。warmup用の追加推論はありません。

3. 校正：第1 waveは8 world、S1/S2・K1/K2・F0/F1の各候補4件、全候補0/4。
   固定同率規則でS1/K1/F0を選び、第2 waveの未使用6 worldでSQL0/6、校正1/6、形成0/6。
   独立referenceは42/42、正常通信完結は54/54ですが、入口ゲートを通ったfamilyはありません。
   有限Nで区間は広く、方式の無効性や同等性を示す結果ではありません。第3 waveや救済samplingはありません。

4. 実行量：screen8、locked validation6、自然stock経路1の計15 world。confirmation0。
   54 calls、実測・chargeとも26,256 tokens、usage欠測0、中断0。driver実測wall1009.437秒、
   先行起動の保守的300秒予約を含むwall charge1309.422秒、cleanup .593秒。
   起動予約は完全な実測値ではなく、nested wallを二重加算していません。256 calls・400,000 charged
   tokens・14,400秒の上限を増やしていません。53品質失敗を全54 offered分母に保持しました。

5. 対応差：confirmationのFull/Empty差およびC/M効果は未推定です。locked SQL・校正・形成の
   restricted秒平均は600 / 501.456 / 600、restricted charged tokens平均は10,240 / 8,601.333 / 10,240。
   実probe wall合計は69.874 / 54.468 / 91.485秒、実tokens合計は2,875 / 2,497 / 3,478です。
   失敗へのrestricted endpoint割当は実消費ではありません。自然stockのM/C各六要求は対応bytesと初期seedが一致。
   学習・transfer全六offerの品質はともに0/6、実tokensはM2,686/C2,674、offer wallはM62.797/C37.313秒。
   M/Cのrestricted平均は共に600秒・10,240 tokensで、記述的対応差は0。実消費のC−Mは−25.484秒・−12 tokensです。
   この1 worldの経路検査は効果推定用Nに加えません。shared-server状態・順序がwallに影響し得ます。

6. 形成と利益：自然形成stockは両armとも空、receiver qualificationは両familyで未成功。
   元providerの物理停止後も全四transferは未成功、各scratch推論1回、検索された実行体0でした。
   固定費・形成・検証・転送等の原記録を保存しましたが、1,677 RPCのphase labelは全てsetupで、
   費目別固定投資のwall帰属は不完全です。親子/RPC latencyをinclusive wallへ二重加算しません。
   H_ACC/H_CIO/H_FORM、追加価値、償却回数、将来保守・energy・全computeは未判定・未推定です。

7. CI・公開：旧0.4.2 gateは新科学sourceの証拠へ転用していません。新unitのcwd欠陥で初回full run
   37141746108が失敗し、原失敗を保持したうえで修正しました。修正版full run37144034341は
   12 native・mixed Python・4 cross reader・readyを通過し、3,819原報告ファイルのhashを認証しました。
   二つのcandidate起源のwheel/sdist bytesは同一で、公開内容は一組です。mainのannotated tag v0.4.3は
   commit5f4165adeb6019a7a7bdc7509b8cc9efb349bfdb、object22ea46e2b803924cf3f245b1055f9a85635cec46。
   標準selectorによるOIDC run37155346028がcandidate/ready/publishを通過しました。tagでnative workloadを
   重複せず、再build・tag移動・skip-existing・旧tag例外はありません。実PyPI bytesを照合し、新規
   no-cache/no-config installで86ファイル・CLI・追加SDK import、実PG/OPA/MCP/A2A/MAFの代表demoを確認。
   ACCEPT・117.00、環境変更後REQUALIFY、依存撤回後REJECT、所有PG停止を確認しました。
   GitHubの8資産を再取得してbytes/sizeを照合。36,418,260-byte ZIP、SHA256
   `22f6d9265d8e625f66973992bd065baadfa8dcf2d7de70281160e5d80d57afc6`の4,910ファイルを検証し、
   ネットワーク遮断・推論なしの再解析が公開verification/analysisと一致しました。旧rawの再梱包やweights公開はありません。
   対象privacy検査は完全な外部監査ではありません。公開前の配置・privacy・guard停止、署名対象でない
   native設定パス6件の変換対応、既存draftのtag参照404も記録し、原科学bytes・署名・CASは保持しました。
