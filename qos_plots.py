# qos_plots.py
# ------------------------------------------------------------
# QoS EXPERIMENT PLOTS AND SUMMARY TABLE
#
# Reads the CSV files produced by qos_experiment.py and writes these to the same folder:
#   1_loss_rate.png             Message loss (%) by scenario and QoS
#   2_latency_distribution.png  Latency distribution (box plot)
#   3_latency_cdf.png           "What percentage of messages arrived within X ms?" curve
#   summary.md                  Summary table that can be copied into a report
#
# Usage:
#   python qos_plots.py                              -> folder of the latest experiment
#   python qos_plots.py results/2026-10-10_17-03-55
# ------------------------------------------------------------

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Draw straight to a file without opening a window
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

# ============================================================
# APPEARANCE SETTINGS
# The colours come from a palette verified to be colour-blind friendly:
# each QoS level has the same colour in every plot.
# ============================================================

QOS_COLOR = {0: "#2a78d6", 1: "#eb6834", 2: "#1baf7a"}  # blue, orange, teal
QOS_NAME = {
    0: "QoS 0 · at most once",
    1: "QoS 1 · at least once",
    2: "QoS 2 · exactly once",
}
SCENARIO_NAME = {"ideal": "Ideal network", "delayed": "Delayed network", "unstable": "Unstable network"}

BACKGROUND = "#fcfcfb"
INK = "#0b0b0b"         # main text colour
SECONDARY = "#52514e"   # axis labels
GRID = "#e1e0d9"        # grid lines
AXIS = "#c3c2b7"        # axis line

plt.rcParams.update({
    "figure.facecolor": BACKGROUND,
    "axes.facecolor": BACKGROUND,
    "savefig.facecolor": BACKGROUND,
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 10,
    "text.color": INK,
    "axes.labelcolor": SECONDARY,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.titlecolor": INK,
    "axes.edgecolor": AXIS,
    "axes.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": SECONDARY,
    "ytick.color": SECONDARY,
    "xtick.major.size": 0,
    "ytick.major.size": 0,
    "legend.frameon": False,
})


# ============================================================
# READING THE DATA
# ============================================================

def find_folder():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    results = Path(__file__).parent / "results"
    folders = sorted(p for p in results.glob("*") if (p / "measurements.csv").exists())
    if not folders:
        sys.exit("ERROR: No results found. Run 'python qos_experiment.py' first.")
    return folders[-1]


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def percentile(sorted_values, p):
    """The p-th percentile of a sorted list (e.g. p=95 -> 95% of values are below it)."""
    if not sorted_values:
        return float("nan")
    return sorted_values[min(len(sorted_values) - 1, int(round(p / 100 * (len(sorted_values) - 1))))]


def prepare_data(folder):
    summary = read_csv(folder / "summary.csv")
    measurements = read_csv(folder / "measurements.csv")

    scenarios = list(dict.fromkeys(s["scenario"] for s in summary))  # keep the order
    qos_levels = sorted({int(s["qos"]) for s in summary})

    # For each (scenario, qos): the repetitions' loss rates, duplicate and disconnect counts
    repetitions = defaultdict(list)
    for s in summary:
        repetitions[(s["scenario"], int(s["qos"]))].append(s)

    # For each (scenario, qos): latencies of the messages across all repetitions (combined)
    latencies = defaultdict(list)
    sent = defaultdict(int)
    for m in measurements:
        key = (m["scenario"], int(m["qos"]))
        sent[key] += 1
        if m["received"] == "1":
            latencies[key].append(float(m["latency_ms"]))
    for values in latencies.values():
        values.sort()

    return scenarios, qos_levels, repetitions, latencies, sent


# ============================================================
# PLOTS
# ============================================================

def add_legend(fig, qos_levels):
    handles = [plt.Line2D([], [], color=QOS_COLOR[q], linewidth=6) for q in qos_levels]
    fig.legend(handles, [QOS_NAME[q] for q in qos_levels], loc="upper center",
               ncol=len(qos_levels), bbox_to_anchor=(0.5, 0.94), fontsize=9, handlelength=1.2)


def loss_plot(folder, scenarios, qos_levels, repetitions):
    fig, ax = plt.subplots(figsize=(8, 4.4))
    width = 0.26
    highest = 0
    for j, q in enumerate(qos_levels):
        for i, s in enumerate(scenarios):
            rates = [float(r["loss_rate_percent"]) for r in repetitions[(s, q)]]
            mean = statistics.fmean(rates)
            x = i + (j - (len(qos_levels) - 1) / 2) * width
            # edgecolor=background: leaves a thin gap between adjacent bars
            ax.bar(x, mean, width, color=QOS_COLOR[q], edgecolor=BACKGROUND, linewidth=1.5)
            if mean == 0:
                # A zero-height bar is invisible; draw a thin line at the base so its colour shows
                ax.plot([x - width * 0.42, x + width * 0.42], [0, 0], color=QOS_COLOR[q],
                        linewidth=3, solid_capstyle="butt", zorder=3)
            if len(rates) > 1 and max(rates) > min(rates):
                # Thin vertical line: the min-max range across repetitions
                ax.plot([x, x], [min(rates), max(rates)], color=INK, linewidth=1)
            highest = max(highest, max(rates))
            label = "0%" if mean == 0 else f"{mean:.1f}%"
            ax.annotate(label, (x, max(rates)), xytext=(0, 4), textcoords="offset points",
                        ha="center", fontsize=8.5, color=SECONDARY)

    ax.set_xticks(range(len(scenarios)), [SCENARIO_NAME.get(s, s) for s in scenarios])
    ax.set_ylabel("Lost messages (%)")
    ax.set_ylim(0, max(5, highest * 1.18))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}%"))
    ax.grid(axis="x", visible=False)
    fig.suptitle("Message loss rate", x=0.06, ha="left", fontweight="bold", fontsize=12)
    add_legend(fig, qos_levels)
    fig.text(0.06, 0.01, "Bar: mean of repetitions · thin line: lowest–highest value across repetitions",
             fontsize=8, color=SECONDARY)
    fig.tight_layout(rect=(0, 0.03, 1, 0.89))
    fig.savefig(folder / "1_loss_rate.png", dpi=200)
    plt.close(fig)


def box_plot(folder, scenarios, qos_levels, latencies):
    fig, axes = plt.subplots(1, len(scenarios), figsize=(10, 4.2))
    for ax, s in zip(axes, scenarios):
        data = [latencies[(s, q)] for q in qos_levels]
        boxes = ax.boxplot(
            data, positions=range(len(qos_levels)), widths=0.55, whis=(5, 95), showfliers=False,
            patch_artist=True, medianprops={"color": INK, "linewidth": 1.5},
            whiskerprops={"color": SECONDARY, "linewidth": 1}, capprops={"color": SECONDARY, "linewidth": 1},
        )
        for box, q in zip(boxes["boxes"], qos_levels):
            box.set_facecolor(QOS_COLOR[q])
            box.set_alpha(0.85)
            box.set_edgecolor(BACKGROUND)
        # The median is written under the QoS name (so nothing overlaps inside the plot)
        labels = [f"QoS {q}\n{statistics.median(v):.3g} ms" if v else f"QoS {q}"
                  for q, v in zip(qos_levels, data)]
        ax.set_xticks(range(len(qos_levels)), labels)
        ax.set_title(SCENARIO_NAME.get(s, s), loc="left")
        ax.set_ylim(bottom=0)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("End-to-end latency (ms)")
    fig.suptitle("Latency distribution", x=0.06, ha="left", fontweight="bold", fontsize=12)
    add_legend(fig, qos_levels)
    fig.text(0.06, 0.01, "Box: middle 50% of messages · thick line and number under the QoS name: median · "
                         "whiskers: 5–95% range · each panel's vertical axis has its own scale", fontsize=8, color=SECONDARY)
    fig.tight_layout(rect=(0, 0.03, 1, 0.89))
    fig.savefig(folder / "2_latency_distribution.png", dpi=200)
    plt.close(fig)


def cdf_plot(folder, scenarios, qos_levels, latencies, sent):
    fig, axes = plt.subplots(1, len(scenarios), figsize=(10, 4.2), sharey=True)
    for ax, s in zip(axes, scenarios):
        for q in qos_levels:
            values = latencies[(s, q)]
            n = sent[(s, q)]
            if not values:
                continue
            # y = share of SENT messages that arrived within this latency.
            # Lost messages never arrive, so the curve can't reach 100%: ceiling = 100 - loss.
            y = [100 * (i + 1) / n for i in range(len(values))]
            ax.step(values, y, where="post", color=QOS_COLOR[q], linewidth=2)
            if y[-1] < 99.95:
                # If there is loss, label the curve's ceiling (how many messages never arrived)
                ax.annotate(f"{y[-1]:.1f}% arrived", (values[-1], y[-1]), xytext=(-4, 8), textcoords="offset points",
                            ha="right", va="bottom", fontsize=8.5, color=SECONDARY)
        ax.set_xscale("log")
        ax.xaxis.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.set_title(SCENARIO_NAME.get(s, s), loc="left")
        ax.set_xlabel("Latency (ms, log scale)")
        ax.set_ylim(0, 104)
        ax.margins(x=0.12)
    axes[0].set_ylabel("Messages arrived (%)")
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}%"))
    fig.suptitle("What share of messages arrived, and how fast?", x=0.06, ha="left", fontweight="bold", fontsize=12)
    add_legend(fig, qos_levels)
    fig.text(0.06, 0.01, "Height where the curve ends = share of messages that arrived (100 − loss). "
                         "Tail to the right = messages that waited out a disconnect and arrived later.",
             fontsize=8, color=SECONDARY)
    fig.tight_layout(rect=(0, 0.03, 1, 0.89))
    fig.savefig(folder / "3_latency_cdf.png", dpi=200)
    plt.close(fig)


# ============================================================
# SUMMARY TABLE
# ============================================================

def summary_table(folder, scenarios, qos_levels, repetitions, latencies):
    rows = [
        "| Scenario | QoS | Loss % (mean) | Loss % (min–max) | Duplicates (mean) | Median (ms) | p95 (ms) | p99 (ms) | Disconnects (mean) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in scenarios:
        for q in qos_levels:
            reps = repetitions[(s, q)]
            loss = [float(r["loss_rate_percent"]) for r in reps]
            duplicates = statistics.fmean(int(r["duplicates"]) for r in reps)
            disconnects = statistics.fmean(int(r["disconnects"]) for r in reps)
            values = latencies[(s, q)]
            rows.append(
                f"| {SCENARIO_NAME.get(s, s)} | {q} | {statistics.fmean(loss):.2f} | {min(loss):.2f}–{max(loss):.2f} | "
                f"{duplicates:.1f} | {statistics.median(values):.2f} | {percentile(values, 95):.2f} | "
                f"{percentile(values, 99):.2f} | {disconnects:.1f} |"
            )
    table = "\n".join(rows)
    (folder / "summary.md").write_text(
        "# QoS experiment summary table\n\n" + table + "\n\n"
        "Latency percentiles are computed over the messages of all repetitions combined. "
        "Loss and duplicate values are the mean of the repetitions.\n",
        encoding="utf-8",
    )
    return table


def main():
    folder = find_folder()
    scenarios, qos_levels, repetitions, latencies, sent = prepare_data(folder)

    loss_plot(folder, scenarios, qos_levels, repetitions)
    box_plot(folder, scenarios, qos_levels, latencies)
    cdf_plot(folder, scenarios, qos_levels, latencies, sent)
    table = summary_table(folder, scenarios, qos_levels, repetitions, latencies)

    print(table)
    print(f"\nPlots and table saved to '{folder}':")
    for file in ["1_loss_rate.png", "2_latency_distribution.png", "3_latency_cdf.png", "summary.md"]:
        print(f"  - {file}")


if __name__ == "__main__":
    main()
