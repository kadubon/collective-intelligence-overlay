"""Render verified analysis into inspectable tables, scientific figures and prose.

This downstream renderer does not verify raw originals or send inference. Run the
offline verifier/analyzer first. The input analysis bytes and rendering manifest
are retained so tables and figures can be traced to that exact derived artifact.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path


def table(rows):
    lines = [
        "| World | Arm | Final Q | Charged tokens | Missing usage |",
        "|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['world']} | {row['arm']} | {row['Q_final_full']:.3f} | "
            f"{row['model_tokens_charged']} | {row['missing_usage']} |"
        )
    return "\n".join(lines)


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {
                k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict | list) else v
                for k, v in row.items()
            }
            for row in rows
        )


def figures(data, output, *, layout_check=False):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update(
        {"font.family": "DejaVu Sans", "font.size": 10, "svg.hashsalt": data["protocol_sha256"]}
    )
    colors = {"E": "#2369ad", "M": "#d97706", "C": "#15803d", "I": "#7e22ce"}
    n = data["independent_worlds"]
    caption = f"Descriptive means; independent N = {n} worlds"
    if layout_check:
        caption = "LAYOUT CHECK: SYNTHETIC VALUES, NO STUDY RESULTS"

    def save(fig, name):
        fig.suptitle(caption, fontsize=10, y=0.995)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        fig.savefig(output / (name + ".png"), dpi=200)
        fig.savefig(
            output / (name + ".svg"),
            metadata={"Date": None, "Creator": "CIO 0.4.2 scientific report"},
        )
        plt.close(fig)

    curves = data["learning_curves"]
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    for arm in sorted({r["arm"] for r in curves}):
        selected = [r for r in curves if r["arm"] == arm]
        checkpoints = sorted({r["checkpoint"] for r in selected})
        for world in sorted({r["world"] for r in selected}):
            rows = sorted(
                (r for r in selected if r["world"] == world), key=lambda r: r["checkpoint"]
            )
            ax.plot(
                [r["declared_training_fraction"] for r in rows],
                [r["Q"] for r in rows],
                color=colors[arm],
                alpha=0.25,
                linewidth=1,
            )
        ax.plot(
            [
                next(r["declared_training_fraction"] for r in selected if r["checkpoint"] == c)
                for c in checkpoints
            ],
            [np.mean([r["Q"] for r in selected if r["checkpoint"] == c]) for c in checkpoints],
            "o-",
            color=colors[arm],
            label=arm,
            linewidth=2,
        )
    ax.set(
        xlabel="Fraction of six declared training episodes",
        ylabel="Fresh-form full-stock Q",
        ylim=(-0.03, 1.03),
    )
    ax.set_xticks([0, 0.5, 1])
    ax.grid(alpha=0.2)
    ax.legend(title="Arm", loc="upper left", bbox_to_anchor=(1.01, 1))
    save(fig, "learning-curves")

    strata = data["family_strata"]
    names = sorted({r["arm"] for r in strata})
    columns = [
        (family, level) for family in ("sql", "calibration") for level in ("low", "middle", "high")
    ]
    values = np.array(
        [
            [
                next(
                    r["mean_Q"]
                    for r in strata
                    if r["arm"] == arm and (r["family"], r["difficulty"]) == c
                )
                for c in columns
            ]
            for arm in names
        ]
    )
    fig, ax = plt.subplots(figsize=(9, 4.2))
    heatmap = ax.imshow(values, vmin=0, vmax=1, cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(columns)), [f"{f}\n{level}" for f, level in columns])
    ax.set_yticks(range(len(names)), names)
    ax.set(title="Final fixed anchor quality by family and difficulty", ylabel="Arm")
    for row in range(len(names)):
        for column in range(len(columns)):
            ax.text(
                column,
                row,
                f"{values[row, column]:.2f}",
                ha="center",
                va="center",
                color="white" if values[row, column] < 0.55 else "black",
            )
    fig.colorbar(heatmap, ax=ax, label="Mean world Q", shrink=0.85)
    save(fig, "family-difficulty")

    formation = data["formation"]
    groups = sorted({(r["arm"], r["view"]) for r in formation})
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for index, (arm, view) in enumerate(groups):
        rows = sorted(
            (r for r in formation if (r["arm"], r["view"]) == (arm, view)), key=lambda r: r["world"]
        )
        offsets = np.linspace(-0.13, 0.13, len(rows))
        for offset, row in zip(offsets, rows, strict=True):
            ax.scatter(
                index + offset,
                row["restricted_time_endpoint"],
                color=colors[arm],
                marker="o" if row["succeeded"] else "x",
                s=48,
            )
        ax.scatter(
            index,
            np.mean([r["restricted_time_endpoint"] for r in rows]),
            color="black",
            marker="_",
            s=180,
        )
    ax.set_xticks(range(len(groups)), [f"{a}\n{v}" for a, v in groups])
    ax.set(
        ylabel="Restricted time to verified formation (seconds)",
        title="Circles: success; crosses: failed finite policy; bars: means",
    )
    ax.set_ylim(bottom=0, top=data["formation_horizon_seconds"] * 1.1)
    ax.grid(axis="y", alpha=0.2)
    save(fig, "formation-restricted-time")

    frontier = data.get("budget_frontier", [])
    if frontier:
        fig, ax = plt.subplots(figsize=(8, 4.8))
        for arm, view in sorted({(r["arm"], r["view"]) for r in frontier}):
            rows = [r for r in frontier if (r["arm"], r["view"]) == (arm, view)]
            budgets = sorted({r["allowed_model_drafts"] for r in rows})
            points = [
                (
                    np.mean(
                        [
                            r["tokens_charged_per_offered_task"]
                            for r in rows
                            if r["allowed_model_drafts"] == b
                        ]
                    ),
                    np.mean([r["Q"] for r in rows if r["allowed_model_drafts"] == b]),
                )
                for b in budgets
            ]
            ax.plot(
                [p[0] for p in points],
                [p[1] for p in points],
                "o-" if view == "full" else "s--",
                color=colors[arm],
                label=f"{arm}/{view}",
            )
            for budget, point in zip(budgets, points, strict=True):
                ax.annotate(str(budget), point, xytext=(4, 5), textcoords="offset points")
        ax.set(
            xlabel="Charged model tokens per offered task",
            ylabel="Fresh-form Q",
            ylim=(-0.03, 1.03),
            title="Numbers mark allowed drafts; complete compute cost unavailable",
        )
        ax.grid(alpha=0.2)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1))
        save(fig, "budget-frontier")


def render(analysis, output):
    raw = analysis.read_bytes()
    data = json.loads(raw)
    if data.get("verified_originals") is not True or data["classification"] not in {
        "calibration",
        "confirmation",
    }:
        raise ValueError("only completed upstream-verified study analysis can be rendered")
    if data["independent_worlds"] < 2:
        raise ValueError("completed independent-world analysis required")
    output.mkdir(parents=True, exist_ok=False)
    (output / "analysis.json").write_bytes(raw)
    for key in (
        "arm_world_rows",
        "learning_curves",
        "strata",
        "family_strata",
        "state_interventions",
        "formation",
        "formation_means",
        "budget_frontier",
        "cost_accounting",
    ):
        write_csv(output / (key.replace("_", "-") + ".csv"), data.get(key, []))
    write_csv(
        output / "contrasts.csv",
        [{"contrast": key, **value} for key, value in data["contrasts"].items()],
    )
    figures(data, output)
    results = table(data["arm_world_rows"])
    primary = data["contrasts"].get("H_CIO_primary_final_Q_C_minus_M")
    primary_text = (
        json.dumps(primary, ensure_ascii=False, indent=2)
        if primary
        else "C/M primary contrast not performed in calibration."
    )
    common = f"\n{results}\n\n```json\n{primary_text}\n```\n"
    english = (
        f"# {data['protocol_id']} — {data['classification']}\n\n"
        f"The independent unit is the world (N={data['independent_worlds']}). "
        "All offered failures remain in their denominators. The primary endpoint is "
        "final fixed-checkpoint C minus M quality; a nonsignificant result does not "
        "establish equivalence. Degenerate bootstrap intervals are unavailable; "
        "the conservative independent-world bound remains visible.\n"
        + common
        + "\nH_SHARE and H_ADAPT are unjudged because I/A were not performed. "
        "Empty or unmatched retained state does not identify a causal placebo effect. "
        "Restricted formation time/resource penalties for failure are separate from "
        "actual observed consumption. See formation and cost tables for marginal and "
        "investment-inclusive endpoints. Missing energy, GPU and complete shared-service "
        "compute are unavailable, so a complete 20% cost benefit is unjudged.\n\n"
        "The figures show the finite synthetic task law on one fixed host/model; "
        "task repetitions do not increase N and this is no universal intelligence or "
        "sustained self-acceleration result. Analysis bytes and renderer versions are "
        "recorded in the manifest. Raw verification is performed upstream by the offline "
        "verifier/analyzer; this renderer makes no network or inference request.\n"
    )
    japanese = (
        f"# {data['protocol_id']} — {data['classification']}\n\n"
        f"独立単位はworldであり、N={data['independent_worlds']}です。"
        "失敗は全offered課題の分母に残します。一次評価は固定した最終checkpointの"
        "C−M品質差です。有意差がないことから同等性は結論しません。退化したbootstrap区間"
        "は利用不能とし、独立worldを仮定する保守的な区間を併記します。\n"
        + common
        + "\nI/Aは未実施のためH_SHARE/H_ADAPTは未判定です。stockが空または無関連対照"
        "の実際の量が対応していない場合、介入の因果効果は識別できません。形成失敗に"
        "対するrestricted time/resourceの上限値は、実測消費とは別のendpointです。"
        "形成・費用表は限界費用と初期投資を含む指標を分けています。energy、GPU、"
        "共有サービスの完全なcomputeは欠測であり、総費用20%削減は未判定です。\n\n"
        "図は固定host/model上の有限なsynthetic課題分布を記述します。taskの反復は"
        "独立Nを増やさず、普遍的知能や持続的な自己加速を示しません。解析の原byteと"
        "描画toolの版はmanifestに残します。原記録は上流のoffline verifier/analyzerで"
        "検証し、このrendererはネットワーク通信や推論を行いません。\n"
    )
    (output / "report.en.md").write_text(english, encoding="utf-8")
    (output / "report.ja.md").write_text(japanese, encoding="utf-8")
    manifest = {
        "protocol_sha256": data["protocol_sha256"],
        "analysis_sha256": hashlib.sha256(raw).hexdigest(),
        "renderer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": sys.version,
        "render_packages": {
            name: importlib.metadata.version(name) for name in ("matplotlib", "numpy")
        },
        "original_verification_is_upstream_analyzer": True,
        "network_or_inference_sent": False,
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())
        },
        "pixel_identity_across_platforms_not_guaranteed": True,
    }
    (output / "render-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.analysis, args.output)


if __name__ == "__main__":
    main()
