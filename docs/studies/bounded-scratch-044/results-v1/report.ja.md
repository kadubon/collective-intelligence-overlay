# v0.4.4 有限手順 pilot

Status: `assay_not_ready`.

両 family が事前規則上の天井に達し、設定を選定できませんでした。G2 と確認比較は未実施です。Full−Empty と C−M の効果は推定していません。

| G1 setting | Quality | 二項 95% 記述区間 | Random | Best constant | 公開文規則 |
| --- | --- | --- | --- | --- | --- |
| sql/L1 | 8/8 | 0.631–1.000 | 25/96 | 26/96 | 96/96 |
| sql/L2 | 8/8 | 0.631–1.000 | 10/96 | 17/96 | 96/96 |
| composition/L1 | 6/8 | 0.349–0.968 | 23/96 | 27/96 | 96/96 |
| composition/L2 | 7/8 | 0.473–0.997 | 14/96 | 15/96 | 96/96 |

区間は広い記述値です。適応的選定・依存があり、確認的な解釈はできません。対照は独立 seed による非モデル診断です。

G0: 実 smoke 4/4、全候補の構文実行・独立 oracle との採点一致 24/24（意味品質 PASS 4・FAIL 20）、正解 reference 36/36。正常通信・schema・構文実行はいずれも 36/36。実モデルで観測した schema は 4/6 です。全 6 種の公開 SDKによる HTTP 直列化は synthetic 応答で確認しました。L0 は未訪問です。

G3: M/C × family の 4 履歴で、G1 の実 Gemma 合格候補を一つずつ新 receiver へ import しました。独立 qualification、元 provider の物理停止、receiver の再起動、同じ artifact/binding の再構成・再検査、Full の copied execution が成立しました。Full は追加推論ゼロ、Empty は検索 stock ゼロで scratch 一要求です。計 8 offered 診断が合格しました。同じ元 world を使う到達性診断であり、独立confirmation N や蓄積利益の対比には含めません。

| Diagnostic history | View | Quality | 独立 PASS までの秒 | PASS までの tokens | 実 wall 秒 |
| --- | --- | --- | --- | --- | --- |
| C/composition | empty | 1 | 3.578 | 715 | 4.203 |
| C/composition | full | 1 | 1.469 | 0 | 1.938 |
| C/sql | empty | 1 | 3.547 | 562 | 4.172 |
| C/sql | full | 1 | 1.359 | 0 | 1.859 |
| M/composition | empty | 1 | 12.063 | 715 | 12.516 |
| M/composition | full | 1 | 1.313 | 0 | 1.704 |
| M/sql | empty | 1 | 14.703 | 562 | 15.047 |
| M/sql | full | 1 | 1.765 | 0 | 2.172 |

全 stage: 実推論 40 件、実測・計上とも 28178 tokens、usage 欠測ゼロ。最終 driver の inclusive wall charge は 2953.683 秒、setup から停止確認までの保守的 charge は 3325.186 秒です。修正待ちを含みます。上限は 256 要求・400000 tokens・14400 秒・同時実行 1。所有 model・observer・PostgreSQL は停止済みで、原データ・log は保持しました。無関係なservice は変更していません。

固定の setup/import/qualification/再起動/cleanup の interval 観測と nested RPC、全オンライン offer の費用は results.json/paired.csv にあります。一部の起動費がinterval 外で、完全な固定 wall 小計は求められません。親 inclusive wall に子 RPC や phase wall を加算しません。未成功の T=300/B=4352 は評価 penalty であり、実消費とは別です。energy・全 compute・将来保守は欠測、F/s は未推定です。

元 pilot の G3 は private-home の衝突で推論前に停止しました。G3-v2 では再起動後に同じ実行 ID へ別入力を渡したため、実行が拒否されました。G3-v3 は新しい実行 ID を事前登録して成立しました。失敗 revision の費用と旧採点を保持し、元 gate を書き換えていません。別 hash の reader が全 3 revision を network・推論なしで検査しました。

元の実 Gemma 候補は 2 個で、別々の 4 owner 履歴へ複製しました。有限手順の再構成と移転であり、算法発明や 4 個の新能力とは呼びません。各 arm が自分の学習経験から作る自然 stock と confirmation 効果は未観測です。公開文を読む非学習手順の100% 対照も保持しました。天井結果は CIO の利益・無効・chance 優勢・同等性のどれも確立していません。

See [methods](../../../bounded-scratch-044.md), [Stage 0](../stage0-v1/summary.json), [all rows](paired.csv), [machine results](results.json), and [release audit](../../../audit-044.md).
