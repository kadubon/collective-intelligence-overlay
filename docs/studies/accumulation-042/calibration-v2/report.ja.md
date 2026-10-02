# cio-042-accumulation-calibration-v2 — calibration

独立単位はworldであり、N=2です。失敗は全offered課題の分母に残します。一次評価は固定した最終checkpointのC−M品質差です。有意差がないことから同等性は結論しません。退化したbootstrap区間は利用不能とし、独立worldを仮定する保守的な区間を併記します。

| World | Arm | Final Q | Charged tokens | Missing usage |
|---|---|---:|---:|---:|
| world-6e8766a70eeb5a077f90 | E | 0.167 | 52781 | 0 |
| world-6e8766a70eeb5a077f90 | M | 0.167 | 68087 | 0 |
| world-e72d6fd2bb3903cd1cf8 | E | 0.167 | 52108 | 0 |
| world-e72d6fd2bb3903cd1cf8 | M | 0.167 | 70378 | 0 |

| Hypothesis | Judgment |
|---|---|
| H_ACC | unjudged_empty_retained_state |
| H_CIO | unjudged_contrast_not_performed |
| H_FORM | unjudged_empty_retained_state |
| H_SHARE | unjudged_I_not_performed |
| H_ADAPT | unjudged_A_not_performed |

```json
C/M primary contrast not performed in calibration.
```

```json
{
  "assay_insensitive": true,
  "family_sensitive_strata": [],
  "legacy_pooled_gate_passed": true,
  "family_review_was_pilot_preregistered": false
}
```

実推論は205 calls、実測tokensは243,354です。model serverの最終停止前のcohort実経過時間は10438.812秒です。familyごとの事後レビューと、当初のpooled校正規則を分離して残します。床のfamilyと天井のfamilyの平均が中間であっても、測定感度は確立しません。
I/Aは未実施のためH_SHARE/H_ADAPTは未判定です。stockが空または無関連対照の実際の量が対応していない場合、介入の因果効果は識別できません。形成失敗に対するrestricted time/resourceの上限値は、実測消費とは別のendpointです。形成・費用表は限界費用と初期投資を含む指標を分けています。energy、GPU、共有サービスの完全なcomputeは欠測であり、総費用20%削減は未判定です。

図は固定host/model上の有限なsynthetic課題分布を記述します。taskの反復は独立Nを増やさず、普遍的知能や持続的な自己加速を示しません。解析の原byteと描画toolの版はmanifestに残します。原記録は上流のoffline verifier/analyzerで検証し、このrendererはネットワーク通信や推論を行いません。
新能力形成は新しい構成の実行体と別のheldout formで評価します。その新能力を新receiverへ移す効果は未測定であり、別transfer panelの対象は学習したSQL/校正手順です。modelのuses IDはcontext参照であり、依存実行による合成の証拠ではありません。
