import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FormatStrFormatter
from sklearn.metrics import confusion_matrix

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH = ROOT / "output" / "accuracy_analysis.csv"
GT_PATH = ROOT / "output" / "groundtruth.jsonl"

RESULT_FILES = {
    "History-RCA": ROOT / "history_rca_result" / "history_rca" / "1771079091917-5662-result.jsonl",
    "MicroRCA": ROOT / "history_rca_result" / "micro_rca" / "micro-4848-result.jsonl",
    "No-History": ROOT / "history_rca_result" / "no_history" / "4983-result.jsonl",
    "Single-Step": ROOT / "history_rca_result" / "single" / "4701-result.jsonl",
}

OFFICIAL_SCORE = {
    "History-RCA": 56.62,
    "MicroRCA": 48.48,
    "No-History": 49.83,
    "Single-Step": 47.01,
}

METHOD_ORDER = ["History-RCA", "MicroRCA", "No-History", "Single-Step"]
MAIN_METHODS = ["History-RCA", "MicroRCA", "Single-Step"]
ABLATION_METHODS = ["History-RCA", "No-History"]

METHOD_DISPLAY = {
    "History-RCA": "History-RCA",
    "MicroRCA": "MicroRCA-Agent",
    "No-History": "w/o History",
    "Single-Step": "Single-Agent with Tools",
}

# Tuned palette: keep baseline methods visually softer than History-RCA.
METHOD_COLORS = {
    "History-RCA": "#4A90E2",
    "MicroRCA": "#E07A5F",
    "No-History": "#90C695",
    "Single-Step": "#B5BDC7",
}

METRICS = [
    ("official_score", "综合得分"),
    ("component_acc", "组件定位准确率 (%)"),
    ("keyword_hit_rate", "根因关键词命中率 (%)"),
    ("both_hit_rate", "联合命中率 (%)"),
]


def set_plot_theme() -> None:
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "#FAFBFD",
            "axes.edgecolor": "#D0D7DE",
            "axes.titleweight": "semibold",
            "axes.titlesize": 16,
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "grid.color": "#E6EAF2",
            "grid.linestyle": "--",
            "grid.linewidth": 0.8,
            "legend.frameon": False,
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Microsoft YaHei",
            ],
            "axes.unicode_minus": False,
        }
    )


def beautify_axis(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D0D7DE")
    ax.spines["bottom"].set_color("#D0D7DE")
    ax.grid(axis="y", alpha=0.8)


def load_jsonl(path: Path) -> List[Dict]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def infer_method(result_file: str) -> str:
    result_file = str(result_file)
    if "/history_rca_result/history_rca/" in result_file:
        return "History-RCA"
    if "/history_rca_result/micro_rca/" in result_file:
        return "MicroRCA"
    if "/history_rca_result/no_history/" in result_file:
        return "No-History"
    if "/history_rca_result/single/" in result_file:
        return "Single-Step"
    return "Unknown"


def load_accuracy_df(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.apply(lambda col: col.map(lambda x: x.strip() if isinstance(x, str) else x))

    numeric_cols = [
        "n",
        "component_hit",
        "component_acc",
        "keyword_hit",
        "keyword_hit_rate",
        "both_hit",
        "both_hit_rate",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["method"] = df["result_file"].apply(infer_method)
    df["official_score"] = df["method"].map(OFFICIAL_SCORE)

    if "match_mode" in df.columns:
        df = df[df["match_mode"] == "exact"].copy()
    return df


def save_table(df: pd.DataFrame, stem: str, caption: str, label: str) -> None:
    csv_path = OUT_DIR / f"{stem}.csv"
    tex_path = OUT_DIR / f"{stem}.tex"
    df.to_csv(csv_path, index=False)

    latex_body = df.to_latex(index=False, float_format=lambda x: f"{x:.2f}", escape=False)
    wrapped = (
        "\\begin{table}[t]\n"
        "\\centering\n"
        f"\\caption{{{caption}}}\n"
        f"\\label{{{label}}}\n"
        f"{latex_body}"
        "\\end{table}\n"
    )
    tex_path.write_text(wrapped, encoding="utf-8")


def format_method_name(method: str) -> str:
    return METHOD_DISPLAY.get(method, method)


def plot_grouped_metrics(
    data: pd.DataFrame,
    methods: List[str],
    out_stem: str,
    annotate_gain: Dict[str, float] = None,
    show_bar_labels: bool = True,
    gain_mode: str = "top",
    color_override: Dict[str, str] = None,
) -> None:
    metrics = [m for m, _ in METRICS]
    metric_labels = [l for _, l in METRICS]

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    x = np.arange(len(metrics))
    width = 0.78 / len(methods)
    start = -0.39 + width / 2

    max_val = 0.0
    history_positions: Dict[str, float] = {}
    history_values: Dict[str, float] = {}
    for i, method in enumerate(methods):
        vals = [float(data.loc[data["method"] == method, m].iloc[0]) for m in metrics]
        max_val = max(max_val, max(vals))
        pos = x + start + i * width
        bars = ax.bar(
            pos,
            vals,
            width=width,
            color=(color_override or METHOD_COLORS)[method],
            label=format_method_name(method),
            edgecolor="white",
            linewidth=1.0,
            alpha=0.95,
        )
        if method == "History-RCA":
            for idx, b in enumerate(bars):
                history_positions[metrics[idx]] = b.get_x() + b.get_width() / 2
                history_values[metrics[idx]] = b.get_height()
        if show_bar_labels:
            for b in bars:
                h = b.get_height()
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    h + 0.55,
                    f"{h:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="#2F3A4A",
                )

    if annotate_gain and "History-RCA" in methods:
        if gain_mode == "top":
            history_pos = x + start + methods.index("History-RCA") * width
            for i, metric in enumerate(metrics):
                gain = annotate_gain.get(metric, 0.0)
                y = float(data.loc[data["method"] == "History-RCA", metric].iloc[0]) + 6.0
                ax.text(
                    history_pos[i],
                    y,
                    f"+{gain:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color="#1F2937",
                )
        elif gain_mode == "inside_history":
            for metric in metrics:
                base_val = history_values.get(metric)
                if base_val is None:
                    continue
                gain = annotate_gain.get(metric, 0.0)
                ax.text(
                    history_positions[metric],
                    max(3.0, base_val * 0.86),
                    f"{base_val:.2f}\n(+{gain:.2f})",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white",
                    fontweight="semibold",
                )

    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels)
    ax.set_ylabel("得分")
    ax.set_ylim(0, min(100, max(70, max_val + 18)))
    ax.legend(ncol=min(4, len(methods)), loc="upper right", fontsize=10)
    beautify_axis(ax)

    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{out_stem}.png", dpi=320, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{out_stem}.pdf", dpi=320, bbox_inches="tight")
    plt.close(fig)


def plot_fault_category_all9(category_df: pd.DataFrame) -> None:
    target_metric = "component_acc"
    order = [
        ("dns fault", "DNS故障"),
        ("erroneous change", "错误变更"),
        ("io fault", "IO故障"),
        ("jvm fault", "JVM故障"),
        ("misconfiguration", "配置错误"),
        ("network attack", "网络攻击"),
        ("node fault", "节点故障"),
        ("pod fault", "Pod故障"),
        ("stress test", "压力测试"),
    ]
    order_keys = [k for k, _ in order]
    order_labels = [v for _, v in order]

    pivot = (
        category_df.pivot(index="fault_category", columns="method", values=target_metric)
        .reindex(order_keys)
        .reindex(columns=METHOD_ORDER)
    )

    export_df = pivot.reset_index().copy()
    export_df.columns = ["fault_category"] + [format_method_name(c) for c in METHOD_ORDER]
    export_df["fault_category"] = export_df["fault_category"].map(dict(order)).fillna(export_df["fault_category"])
    for col in export_df.columns[1:]:
        export_df[col] = export_df[col].map(lambda v: "" if pd.isna(v) else f"{float(v):.2f}")
    export_df.to_csv(OUT_DIR / "tab3_fault_category_component_acc.csv", index=False)

    fig, ax = plt.subplots(figsize=(10.4, 5.8))
    x = np.arange(len(order_keys))
    marker_map = {
        "History-RCA": "o",
        "MicroRCA": "s",
        "No-History": "^",
        "Single-Step": "D",
    }
    linestyle_map = {
        "History-RCA": "-",
        "MicroRCA": "--",
        "No-History": "-.",
        "Single-Step": ":",
    }

    for method in METHOD_ORDER:
        vals = pivot[method].to_numpy(dtype=float)
        ax.plot(
            x,
            vals,
            label=format_method_name(method),
            color=METHOD_COLORS[method],
            marker=marker_map[method],
            linestyle=linestyle_map[method],
            linewidth=2.0,
            markersize=5.2,
            alpha=0.95,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(order_labels, rotation=22, ha="right")
    ax.set_ylabel("组件定位准确率 (%)")
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    max_val = float(np.nanmax(pivot.to_numpy(dtype=float))) if not pivot.empty else 0.0
    ax.set_ylim(0, min(100, max(70, max_val + 8)))
    ax.legend(ncol=2, loc="upper left", fontsize=9)
    beautify_axis(ax)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig3_fault_category_all9.png", dpi=320, bbox_inches="tight")
    fig.savefig(OUT_DIR / "fig3_fault_category_all9.pdf", dpi=320, bbox_inches="tight")
    plt.close(fig)


def normalize_label(name: str) -> str:
    if name is None:
        return "unknown"
    s = str(name).strip().lower()
    if not s:
        return "unknown"

    if s.startswith("aiops-k8s-"):
        return "k8s-node"

    known_tokens = [
        "adservice",
        "cartservice",
        "checkoutservice",
        "currencyservice",
        "emailservice",
        "frontend",
        "paymentservice",
        "productcatalogservice",
        "recommendationservice",
        "shippingservice",
        "redis-cart",
        "redis-order",
        "tidb-tikv",
        "tidb-tidb",
        "tidb-pd",
        "coredns",
    ]
    for token in known_tokens:
        if token in s:
            return token

    s = re.sub(r"-[a-f0-9]{8,}$", "", s)
    s = re.sub(r"-\d+$", "", s)
    return s


COMPONENT_DISPLAY = {
    "adservice": "广告服务",
    "cartservice": "购物车服务",
    "checkoutservice": "结账服务",
    "currencyservice": "货币服务",
    "emailservice": "邮件服务",
    "frontend": "前端服务",
    "paymentservice": "支付服务",
    "productcatalogservice": "商品目录服务",
    "recommendationservice": "推荐服务",
    "shippingservice": "物流服务",
    "redis-cart": "Redis-购物车",
    "redis-order": "Redis-订单",
    "tidb-tikv": "TiDB-TiKV",
    "tidb-tidb": "TiDB-Server",
    "tidb-pd": "TiDB-PD",
    "coredns": "CoreDNS",
    "k8s-node": "K8s节点",
    "other": "其他",
    "unknown": "未知",
}


def format_component_label(label: str) -> str:
    return COMPONENT_DISPLAY.get(label, label)


def choose_gt_primary_instance(item: Dict) -> str:
    service = str(item.get("service", "")).strip()
    source = str(item.get("source", "")).strip()
    inst = item.get("instance", "")

    if service:
        return service
    if source:
        return source
    if isinstance(inst, list) and inst:
        return str(inst[0])
    return str(inst)


def build_confusion_matrix() -> None:
    gt = {x["uuid"]: x for x in load_jsonl(GT_PATH)}
    pred = {x["uuid"]: x for x in load_jsonl(RESULT_FILES["History-RCA"])}

    y_true = []
    y_pred = []
    for uid, gt_item in gt.items():
        if uid not in pred:
            continue
        true_label = normalize_label(choose_gt_primary_instance(gt_item))
        pred_label = normalize_label(pred[uid].get("component", ""))
        y_true.append(true_label)
        y_pred.append(pred_label)

    top_labels = [k for k, _ in Counter(y_true).most_common(12)]
    labels = top_labels + ["other"]

    y_true_mapped = [x if x in top_labels else "other" for x in y_true]
    y_pred_mapped = [x if x in top_labels else "other" for x in y_pred]

    cm = confusion_matrix(y_true_mapped, y_pred_mapped, labels=labels)
    cm_norm = cm.astype(float) / np.clip(cm.sum(axis=1, keepdims=True), a_min=1.0, a_max=None)

    display_labels = [format_component_label(x) for x in labels]
    cm_df = pd.DataFrame(cm_norm, index=display_labels, columns=display_labels)
    cm_df.to_csv(OUT_DIR / "tab4_confusion_matrix_normalized.csv")

    fig, ax = plt.subplots(figsize=(10.2, 8.8))
    cmap = sns.color_palette("blend:#f7fbff,#2b6cb0", as_cmap=True)
    sns.heatmap(
        cm_df,
        cmap=cmap,
        vmin=0,
        vmax=1,
        square=True,
        linewidths=0.45,
        linecolor="#E6EAF2",
        cbar_kws={"label": "得分"},
        ax=ax,
    )

    for i in range(cm_df.shape[0]):
        for j in range(cm_df.shape[1]):
            v = cm_df.iloc[i, j]
            if v >= 0.18:
                ax.text(
                    j + 0.5,
                    i + 0.5,
                    f"{v:.2f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white" if v > 0.5 else "#1F2937",
                )

    ax.set_xlabel("预测组件")
    ax.set_ylabel("真实组件")
    ax.tick_params(axis="x", rotation=90)
    ax.tick_params(axis="y", rotation=0)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig4_service_confusion_matrix.png", dpi=320, bbox_inches="tight")
    fig.savefig(OUT_DIR / "fig4_service_confusion_matrix.pdf", dpi=320, bbox_inches="tight")
    plt.close(fig)


def is_component_hit(pred_component: str, gt_instance) -> bool:
    pred = str(pred_component).strip().lower()
    if isinstance(gt_instance, str):
        gt_list = [gt_instance]
    else:
        gt_list = [str(x) for x in gt_instance]

    for g in gt_list:
        gs = g.strip().lower()
        if gs == pred:
            return True
    return False


def compute_subset_acc(result_path: Path, gt_map: Dict[str, Dict], subset: set) -> Tuple[float, int]:
    pred_map = {x["uuid"]: x for x in load_jsonl(result_path)}
    correct, total = 0, 0
    for uid in subset:
        if uid not in gt_map or uid not in pred_map:
            continue
        total += 1
        if is_component_hit(pred_map[uid].get("component", ""), gt_map[uid].get("instance", "")):
            correct += 1
    acc = 100.0 * correct / total if total else 0.0
    return acc, total


def build_generalization_results() -> pd.DataFrame:
    gt_map = {x["uuid"]: x for x in load_jsonl(GT_PATH)}
    seen = {
        x.strip()
        for x in (ROOT / "splits" / "seen_test_uuids.txt").read_text(encoding="utf-8").splitlines()
        if x.strip()
    }
    unseen = {
        x.strip()
        for x in (ROOT / "splits" / "unseen_test_uuids.txt").read_text(encoding="utf-8").splitlines()
        if x.strip()
    }

    rows = []
    for method in METHOD_ORDER:
        seen_acc, seen_n = compute_subset_acc(RESULT_FILES[method], gt_map, seen)
        unseen_acc, unseen_n = compute_subset_acc(RESULT_FILES[method], gt_map, unseen)
        rows.append(
            {
                "method": method,
                "seen_acc": round(seen_acc, 2),
                "seen_n": seen_n,
                "unseen_acc": round(unseen_acc, 2),
                "unseen_n": unseen_n,
                "seen_minus_unseen": round(seen_acc - unseen_acc, 2),
            }
        )

    df = pd.DataFrame(rows)
    df["_order"] = df["method"].apply(lambda x: METHOD_ORDER.index(x))
    return df.sort_values("_order").drop(columns=["_order"])


def plot_generalization(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    groups = ["已知故障子集", "未知故障子集"]
    x = np.arange(len(groups))
    width = 0.18
    start = -1.5 * width

    for i, method in enumerate(METHOD_ORDER):
        row = df[df["method"] == method].iloc[0]
        vals = [row["seen_acc"], row["unseen_acc"]]
        pos = x + start + i * width
        bars = ax.bar(
            pos,
            vals,
            width=width,
            color=METHOD_COLORS[method],
            label=format_method_name(method),
            edgecolor="white",
            linewidth=1.0,
        )
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h + 0.8, f"{h:.2f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(groups, rotation=0)
    ax.set_ylabel("组件定位准确率 (%)")
    ax.set_ylim(0, 105)
    ax.legend(fontsize=9, loc="upper left", ncol=2)
    beautify_axis(ax)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig5_seen_unseen_generalization.png", dpi=320, bbox_inches="tight")
    fig.savefig(OUT_DIR / "fig5_seen_unseen_generalization.pdf", dpi=320, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    set_plot_theme()
    df = load_accuracy_df(CSV_PATH)

    overall = df[(df["scope"] == "overall") & (df["fault_category"] == "ALL")].copy()
    category = df[df["scope"] == "fault_category"].copy()

    overall = overall[["method", "n", "official_score", "component_acc", "keyword_hit_rate", "both_hit_rate"]]
    overall = overall[overall["method"].isin(METHOD_ORDER)].copy()

    # 1) Main results (non-ablation methods)
    main_df = overall[overall["method"].isin(MAIN_METHODS)].copy()
    main_df["_order"] = main_df["method"].apply(lambda x: MAIN_METHODS.index(x))
    main_df = main_df.sort_values("_order").drop(columns=["_order"])

    baseline_df = main_df[main_df["method"] != "History-RCA"]
    gains = {}
    for metric, _ in METRICS:
        gains[metric] = float(main_df.loc[main_df["method"] == "History-RCA", metric].iloc[0] - baseline_df[metric].max())

    tab1 = main_df.copy()
    tab1["method"] = tab1["method"].map(format_method_name)
    gain_row = {
        "method": "Gain vs Best Baseline",
        "n": np.nan,
        "official_score": round(gains["official_score"], 2),
        "component_acc": round(gains["component_acc"], 2),
        "keyword_hit_rate": round(gains["keyword_hit_rate"], 2),
        "both_hit_rate": round(gains["both_hit_rate"], 2),
    }
    tab1 = pd.concat([tab1, pd.DataFrame([gain_row])], ignore_index=True)
    tab1 = tab1.rename(
        columns={
            "method": "Method",
            "n": "Cases",
            "official_score": "Official Score",
            "component_acc": "Component Acc (%)",
            "keyword_hit_rate": "Keyword Hit Rate (%)",
            "both_hit_rate": "Both Hit Rate (%)",
        }
    )
    tab1["Cases"] = tab1["Cases"].apply(lambda x: "" if pd.isna(x) else str(int(x)))
    save_table(tab1, "tab1_overall_non_ablation", "Overall results on 400 cases (excluding ablation).", "tab:overall_non_ablation")
    plot_grouped_metrics(
        main_df,
        MAIN_METHODS,
        "fig1_overall_non_ablation",
        annotate_gain=None,
        show_bar_labels=True,
        color_override={
            "History-RCA": "#4A90E2",
            "MicroRCA": "#E07A5F",
            "Single-Step": "#B5BDC7",
        },
    )

    # 2) Ablation results
    ablation_df = overall[overall["method"].isin(ABLATION_METHODS)].copy()
    ablation_df["_order"] = ablation_df["method"].apply(lambda x: ABLATION_METHODS.index(x))
    ablation_df = ablation_df.sort_values("_order").drop(columns=["_order"])

    delta = {}
    for metric, _ in METRICS:
        ours = float(ablation_df.loc[ablation_df["method"] == "History-RCA", metric].iloc[0])
        no_hist = float(ablation_df.loc[ablation_df["method"] == "No-History", metric].iloc[0])
        delta[metric] = ours - no_hist

    tab2 = ablation_df.copy()
    tab2["method"] = tab2["method"].map(format_method_name)
    ab_gain_row = {
        "method": "Delta (History-RCA - w/o History)",
        "n": np.nan,
        "official_score": round(delta["official_score"], 2),
        "component_acc": round(delta["component_acc"], 2),
        "keyword_hit_rate": round(delta["keyword_hit_rate"], 2),
        "both_hit_rate": round(delta["both_hit_rate"], 2),
    }
    tab2 = pd.concat([tab2, pd.DataFrame([ab_gain_row])], ignore_index=True)
    tab2 = tab2.rename(
        columns={
            "method": "Method",
            "n": "Cases",
            "official_score": "Official Score",
            "component_acc": "Component Acc (%)",
            "keyword_hit_rate": "Keyword Hit Rate (%)",
            "both_hit_rate": "Both Hit Rate (%)",
        }
    )
    tab2["Cases"] = tab2["Cases"].apply(lambda x: "" if pd.isna(x) else str(int(x)))
    save_table(tab2, "tab2_ablation", "Ablation results on 400 cases.", "tab:ablation")
    plot_grouped_metrics(
        ablation_df,
        ABLATION_METHODS,
        "fig2_ablation",
        annotate_gain=None,
        show_bar_labels=True,
        gain_mode="top",
    )

    # 3) Performance by all 9 fault categories
    plot_fault_category_all9(category)

    # 4) Service-level confusion matrix
    build_confusion_matrix()

    # 5) Seen vs unseen generalization
    gen_df = build_generalization_results()
    export_gen = gen_df.copy()
    export_gen["method"] = export_gen["method"].map(format_method_name)
    export_gen = export_gen.rename(
        columns={
            "method": "Method",
            "seen_acc": "Seen Acc (%)",
            "seen_n": "Seen N",
            "unseen_acc": "Unseen Acc (%)",
            "unseen_n": "Unseen N",
            "seen_minus_unseen": "Seen - Unseen (pp)",
        }
    )
    save_table(
        export_gen,
        "tab5_seen_unseen_generalization",
        "Generalization results on seen and unseen fault subsets.",
        "tab:generalization",
    )
    plot_generalization(gen_df)

    print("Generated artifacts:")
    print("- tab1_overall_non_ablation(.csv/.tex), fig1_overall_non_ablation(.png/.pdf)")
    print("- tab2_ablation(.csv/.tex), fig2_ablation(.png/.pdf)")
    print("- tab3_fault_category_component_acc.csv, fig3_fault_category_all9(.png/.pdf)")
    print("- tab4_confusion_matrix_normalized.csv, fig4_service_confusion_matrix(.png/.pdf)")
    print("- tab5_seen_unseen_generalization(.csv/.tex), fig5_seen_unseen_generalization(.png/.pdf)")


if __name__ == "__main__":
    main()
