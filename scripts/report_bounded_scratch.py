"""Generate finite 0.4.4 tables from separately verified originals; no inference."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from near_transfer_protocol import sha

from collective_intelligence_overlay.adapters.inference_observer import write_new


def generate(runs, analyses, cleanup, output):
    verified = [json.loads((p / "analysis.json").read_bytes()) for p in analyses]
    if not all(v["verification"] == "passed" and not v["pending"] for v in verified):
        raise ValueError("all original runs must have complete offline verification")
    pilot, _, stock = verified
    original_summary = json.loads((runs[0] / "pilot-summary.json").read_bytes())
    candidate_checks = [json.loads(p.read_bytes()) for p in runs[0].rglob("*-candidate-*.json")]
    rows = []
    intervals = defaultdict(lambda: {"observations": 0, "nested_wall_seconds": 0.0})
    for index, (run, value) in enumerate(zip(runs, verified, strict=True)):
        rows.extend({"run_revision": index + 1, **r} for r in value["all_offered_rows"])
        for path in run.rglob("phase-intervals.json"):
            for item in json.loads(path.read_bytes()):
                group = intervals[item["phase"] + "/" + item["cost_scope"]]
                group["observations"] += 1
                group["nested_wall_seconds"] += item["inclusive_wall_seconds"]
    resources = json.loads((runs[-1] / "resources.json").read_bytes())
    stopped = json.loads(cleanup.read_bytes())
    if resources["model_calls"] != sum(v["generation_calls"] for v in verified):
        raise ValueError("global call denominator changed")
    if resources["charged_tokens"] != sum(v["charged_tokens"] for v in verified):
        raise ValueError("global token denominator changed")
    if (
        not all(d["ready"] for d in stock["stock_diagnostics"])
        or len(stock["stock_diagnostics"]) != 4
    ):
        raise ValueError("G3 requires four completed paths")
    screen = {k: v for k, v in pilot["screen"].items() if v["offered"]}
    result = {
        "classification": "pilot_and_path_diagnostic_not_confirmation",
        "status": "assay_not_ready",
        "stop_reason": "both_families_reached_preregistered_ceiling_no_setting_selected",
        "G0": {
            "native_smoke": {
                "passed": sum(r["succeeded"] for r in original_summary["smoke"]),
                "offered": len(original_summary["smoke"]),
            },
            "native_schema_shapes": 4,
            "declared_schema_shapes": 6,
            "synthetic_public_SDK_schema_shapes": 6,
            "all_candidate_controls": {
                "passed": sum(bool(c.get("check")) for c in candidate_checks),
                "offered": len(candidate_checks),
                "metric": "executability_and_agreement_with_independent_semantic_oracle",
                "semantic_quality_passed": sum(c["succeeded"] for c in candidate_checks),
                "semantic_quality_failed": sum(not c["succeeded"] for c in candidate_checks),
            },
            "per_offer_reference_controls": {
                "passed": sum(r["succeeded"] for r in original_summary["reference"]),
                "offered": len(original_summary["reference"]),
            },
            "normal": pilot["normal"],
            "schema": sum(r["schema"] is True for r in pilot["all_offered_rows"]),
            "executable": sum(r["executable"] is True for r in pilot["all_offered_rows"]),
            "all_declared_schemas_native_observed": False,
        },
        "G1": screen,
        "G2": {"offered": 0, "selected": {}, "not_started": True},
        "G3": stock["stock_diagnostics"],
        "G3_failed_revision": verified[1]["stock_diagnostics"],
        "controls": pilot["screen_controls"],
        "confirmation_worlds": 0,
        "confirmation_started": False,
        "H_ACC": "not_estimated",
        "H_CIO": "not_estimated",
        "H_FORM": "not_estimated",
        "chance_dominated_or_unresolved": "not_established_by_this_ceiling_pilot",
        "limited_power": "descriptive_small_samples_no_effect_or_equivalence_inference",
        "stock_scope": {"native_source_candidates": 2, "separate_arm_histories": 4},
        "generation_requests": resources["model_calls"],
        "measured_tokens": resources["measured_tokens"],
        "charged_tokens": resources["charged_tokens"],
        "missing_usage_requests": resources["missing_usage_requests"],
        "global_resources": resources,
        "cleanup": stopped,
        "normal_cleanup_inclusive_charge_seconds": stopped["inclusive_charge_seconds"],
        "phase_interval_observations": dict(intervals),
        "phase_intervals_and_RPC_are_nested_not_added_to_global_wall": True,
        "fixed_cost_scope": "setup/reference/construction/import/qualification/restart/cleanup",
        "online_cost_scope": "all 44 offered rows; G3 rows are mechanism diagnostics",
        "fixed_total_wall_identifiable": False,
        "fixed_wall_limit": "intervals omit some process startup and may overlap; no residual ROI",
        "break_even": None,
        "energy_joules": None,
        "full_compute": None,
        "future_maintenance": None,
        "inputs": [
            {
                "run": run.name,
                "protocol_sha256": sha(run / "protocol.json"),
                "resources_sha256": sha(run / "resources.json"),
                "analysis_sha256": sha(analysis / "analysis.json"),
                "reader_sha256": value["reader_sha256"],
            }
            for run, analysis, value in zip(runs, analyses, verified, strict=True)
        ],
    }
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "results.json", result)
    for index, analysis in enumerate(analyses, 1):
        (output / f"verification-{index}.json").write_bytes(
            (analysis / "analysis.json").read_bytes()
        )
    with (output / "paired.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for language in ("en", "ja"):
        title = "Bounded procedure pilot" if language == "en" else "有限手順 pilot"
        paragraphs = (
            "Both families reached the declared "
            "ceiling. No setting was selected; G"
            "2 and "
            "confirmation were not started. No F"
            "ull−Empty or C−M effect is estimate"
            "d."
            if language == "en"
            else "両 family が事前規則上の天井に達し、設定を選定できませんでした。G2 と確認比較は"
            "未実施です。Full−Empty と C−M の効果は推定していません。"
        )
        text = [f"# v0.4.4 {title}", "", "Status: `assay_not_ready`.", "", paragraphs, ""]
        text += [
            "| G1 setting | Quality | Exact bino"
            "mial 95% interval | Random | Best c"
            "onstant | "
            "Public-text rule |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for setting, value in screen.items():
            control = result["controls"][setting]
            lo, hi = value["exact_binomial_95_interval"]
            text.append(
                f"| {setting} | {value['passed']}/{value['offered']} | {lo:.3f}–{hi:.3f} | "
                f"{control['uniform_random']['passed']}/96 | "
                f"{control['best_constant']['passed']}/96 | "
                f"{control['semantic_rule']['passed']}/96 |"
            )
        text += [
            "",
            "Intervals are descriptive and broad"
            "; adaptive selection/dependence pre"
            "vents a "
            "confirmatory interpretation. Contro"
            "ls use independent seeds and no mod"
            "el inference."
            if language == "en"
            else "区間は広い記述値です。適応的選定・依存があり、確認的な解釈はできません。対照は"
            "独立 seed による非モデル診断です。",
            "",
            "G0: native smoke 4/4, candidate exe"
            "cutability/score agreement 24/24 "
            "(semantic quality PASS 4, FAIL 20),"
            " per-offer references 36/36; "
            "normal/schema/executable 36/36. Nat"
            "ive schema coverage is 4/6; all six"
            " were "
            "serialized using the public SDK wit"
            "h synthetic responses. L0 was not v"
            "isited.",
            "",
            "G3: four independent M/C × family h"
            "istories, each importing one actual"
            " passed "
            "native G1 candidate into a fresh re"
            "ceiver. Qualification, physical pro"
            "vider stop, "
            "receiver restart with unchanged art"
            "ifact/binding, independent check an"
            "d Full "
            "copied execution succeeded. Full us"
            "ed zero model calls; Empty retrieve"
            "d zero "
            "skills and made one scratch call. A"
            "ll eight diagnostic offers passed. "
            "These "
            "repeated source worlds are not inde"
            "pendent confirmation N or a benefit"
            " contrast.",
            "",
            "| Diagnostic history | View | Quali"
            "ty | Time to first independent PASS"
            " (s) | "
            "Tokens to PASS | Actual wall (s) |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in stock["all_offered_rows"]:
            text.append(
                f"| {row['arm']}/{row['family']} | {row['view']} | {row['Q']} | "
                f"{row['restricted_time_seconds']:.3f} | {row['restricted_charged_tokens']} | "
                f"{row['actual_wall_seconds']:.3f} |"
            )
        text += [
            "",
            f"All stages: {result['generation_requests']} real requests, "
            f"{result['measured_tokens']} measured/charged tokens, zero missing usage. "
            f"The last driver charged {resources['inclusive_wall_seconds']:.3f} s; "
            f"the conservative setup-through-confirmed-cleanup bound is "
            f"{stopped['inclusive_charge_seconds']:.3f} s, including intervening repair time. "
            "Caps: 256 requests, 400000 tokens, "
            "14400 s, serial one. Owned model, o"
            "bserver and "
            "PostgreSQL stopped; private data/lo"
            "gs are retained and unrelated servi"
            "ces untouched.",
            "",
            "Fixed setup/import/qualification/re"
            "start/cleanup interval observations"
            ", nested "
            "RPC costs and every online offer ar"
            "e in results.json/paired.csv. Some "
            "process "
            "startup is outside phase intervals;"
            " a complete fixed-wall subtotal is "
            "unavailable. "
            "Do not add nested RPC/phase wall to"
            " inclusive wall. Unsuccessful endpo"
            "ints use "
            "T=300/B=4352 as penalties separatel"
            "y from actual consumption. Energy, "
            "full compute "
            "and future maintenance are missing; F/s is unestimated.",
            "",
            "Original pilot G3 failed before inf"
            "erence due to a private-home collis"
            "ion. "
            "G3-v2 preserved a second pre-offer "
            "failure: an unchanged execution ID "
            "was reused "
            "with new inputs after restart. G3-v"
            "3 preregistered the fresh ID and pa"
            "ssed; all "
            "failed resources and original score"
            "s remain included. Frozen original "
            "gate fields "
            "are not rewritten. The separately h"
            "ashed reader verifies all three rev"
            "isions "
            "without network or inference.",
            "",
            "Two actual native candidates were c"
            "opied into four separate histories."
            " This is "
            "bounded procedure reconstruction/tr"
            "ansfer, not algorithm invention or "
            "four new "
            "abilities. Natural independent trai"
            "ning stock and confirmation effects"
            " remain "
            "unobserved. The 100% public-text ba"
            "seline is retained. This ceiling re"
            "sult neither "
            "establishes CIO benefit nor CIO ine"
            "ffectiveness, chance domination or "
            "equivalence.",
            "",
            "See [methods](../../../bounded-scratch-044.md), "
            "[Stage 0](../stage0-v1/summary.json"
            "), [all rows](paired.csv), "
            "[machine results](results.json), an"
            "d [release audit](../../../audit-04"
            "4.md).",
            "",
        ]
        if language == "ja":
            translated = []
            for paragraph in text:
                if paragraph.startswith("G0:"):
                    paragraph = (
                        "G0: 実 smoke 4/4、全候補の構文実行・"
                        "独立 oracle との採点一致 24/24"
                        "（意味品質 PASS 4・FAIL 20）、正解 "
                        "reference "
                        "36/36。正常通信・schema・構文実行"
                        "はいずれも 36/36。実モデルで観測した sch"
                        "ema は 4/6 "
                        "です。全 6 種の公開 SDK"
                        "による HTTP 直列化は synthetic 応"
                        "答で確認しました。L0 は未訪問です。"
                    )
                elif paragraph.startswith("G3:"):
                    paragraph = (
                        "G3: M/C × family の 4 履歴で、"
                        "G1 の実 Gemm"
                        "a 合格候補を一つずつ新 receiver "
                        "へ import しました。独立 qualific"
                        "ation、元 pr"
                        "ovider の物理停止、receiver の"
                        "再起動、同じ artifact/binding の"
                        "再構成・再検査、Fu"
                        "ll の copied execution が成立"
                        "しました。Full は追加推論ゼロ、Empty は"
                        "検索 stock ゼ"
                        "ロで scratch 一要求です。"
                        "計 8 offered 診断が合格しました。同じ元"
                        " world を使う到達性診断であり、独立"
                        "confirmation N や蓄積利益の対比には含めません。"
                    )
                elif paragraph.startswith("All stages:"):
                    paragraph = (
                        f"全 stage: 実推論 {result['generation_requests']} 件、実測・計上とも "
                        f"{result['measured_tokens']} tokens、usage 欠測ゼロ。"
                        "最終 driver の inclusive "
                        f"wall charge は {resources['inclusive_wall_seconds']:.3f} 秒、"
                        "setup から停止確認"
                        f"までの保守的 charge は {stopped['inclusive_charge_seconds']:.3f} 秒です。"
                        "修正待ち"
                        "を含みます。上限は 256 要求・400000 t"
                        "okens・1440"
                        "0 秒・同時実行 1。所有 model・"
                        "observer・PostgreSQL は停止済み"
                        "で、原データ・log は保持しました。無関係な"
                        "service は変更していません。"
                    )
                elif paragraph.startswith("Fixed setup/"):
                    paragraph = (
                        "固定の setup/import/qualific"
                        "ation/再起動/"
                        "cleanup の interval 観測と nested RPC、"
                        "全オンライン offer の費用は results"
                        ".json/pair"
                        "ed.csv にあります。一部の起動費が"
                        "interval 外で、完全な固定 wall 小計"
                        "は求められません。親"
                        " inclusive wall に子 RPC "
                        "や phase wall を加算しません。未成功の"
                        " T=300/B=4"
                        "352 は評価 penalty であり、"
                        "実消費とは別です。energy・全 compute"
                        "・将来保守は欠測、F/s は未推定です。"
                    )
                elif paragraph.startswith("Original pilot"):
                    paragraph = (
                        "元 pilot の G3 は private-ho"
                        "me の衝突で推論前"
                        "に停止しました。G3-v2 では再起動後"
                        "に同じ実行 ID へ別入力を渡したため、実行が拒否"
                        "されました。G3-v3 は新しい実行 ID "
                        "を事前登録して成立しました。失敗 revision"
                        " の費用と旧採点を保持し、元 gate を"
                        "書き換えていません。別 hash の reader"
                        " が全 3 revi"
                        "sion を network・推論なしで"
                        "検査しました。"
                    )
                elif paragraph.startswith("Two actual"):
                    paragraph = (
                        "元の実 Gemma 候補は 2 個で、別々の 4 "
                        "owner 履歴へ複製しました。有限手順の再構成"
                        "と移転であり、算法発明や 4 個の新能力とは呼びま"
                        "せん。各 arm が自分の学習経験"
                        "から作る自然 stock と confirmati"
                        "on 効果は未観測です。公開文を読む非学習手順の"
                        "100% 対照も保持しました。天井結果は CIO "
                        "の利益・無効・chance 優勢・同等性の"
                        "どれも確立していません。"
                    )
                paragraph = paragraph.replace("Exact binomial 95% interval", "二項 95% 記述区間")
                paragraph = paragraph.replace("Public-text rule", "公開文規則")
                paragraph = paragraph.replace(
                    "Time to first independent PASS (s)", "独立 PASS までの秒"
                )
                paragraph = paragraph.replace("Tokens to PASS", "PASS までの tokens")
                paragraph = paragraph.replace("Actual wall (s)", "実 wall 秒")
                translated.append(paragraph)
            text = translated
        (output / f"report.{language}.md").write_text(
            "\n".join(text), encoding="utf-8", newline="\n"
        )
    print(
        json.dumps(
            {
                "status": result["status"],
                "offered": len(rows),
                "generation_requests": result["generation_requests"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs=3, required=True)
    parser.add_argument("--analyses", type=Path, nargs=3, required=True)
    parser.add_argument("--cleanup", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.runs, args.analyses, args.cleanup, args.output)
