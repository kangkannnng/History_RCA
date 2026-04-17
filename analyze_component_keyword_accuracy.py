#!/usr/bin/env python3
"""
组件准确率与根因关键词命中率分析（批量模式）

统计口径：
1) 组件准确率（component_accuracy）
   - 按 uuid 将结果文件与 GT 对齐
   - 判断 result.component 是否命中 gt.instance
   - gt.instance 可能是字符串或字符串列表；列表场景命中任意一个即为正确

2) 根因关键词命中率（keyword_hit_rate）
   - 判断 result.reason 是否包含 gt.key_metrics 中任意关键词
   - gt.key_metrics 为关键词集合（非严格监控指标语义）
   - 命中任意一个即为正确

默认组件匹配模式为 contains（任意一侧包含即命中，不区分大小写）。
可选 exact 模式做严格名称匹配。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
	data: List[Dict[str, Any]] = []
	with path.open("r", encoding="utf-8") as f:
		for line_no, line in enumerate(f, start=1):
			line = line.strip()
			if not line:
				continue
			try:
				data.append(json.loads(line))
			except json.JSONDecodeError as exc:
				raise ValueError(f"JSONL 解析失败: {path} 第 {line_no} 行: {exc}") from exc
	return data


def as_list(value: Any) -> List[str]:
	if value is None:
		return []
	if isinstance(value, list):
		return [str(v).strip() for v in value if str(v).strip()]
	text = str(value).strip()
	return [text] if text else []


def normalize_text(s: str) -> str:
	return s.strip().lower()


def component_match(component: str, instances: Iterable[str], mode: str = "exact") -> bool:
	c = normalize_text(component)
	if not c:
		return False

	norm_instances = [normalize_text(x) for x in instances if str(x).strip()]
	if not norm_instances:
		return False

	if mode == "exact":
		return any(c == inst for inst in norm_instances)

	return any(c in inst or inst in c for inst in norm_instances)


def keyword_hit(reason: str, key_metrics: Iterable[str]) -> bool:
	r = normalize_text(reason)
	if not r:
		return False

	for kw in key_metrics:
		kw_norm = normalize_text(str(kw))
		if kw_norm and kw_norm in r:
			return True
	return False


def init_counter() -> Dict[str, int]:
	return {
		"total": 0,
		"component_hit": 0,
		"keyword_hit": 0,
		"both_hit": 0,
	}


def update_counter(counter: Dict[str, int], comp_ok: bool, kw_ok: bool) -> None:
	counter["total"] += 1
	if comp_ok:
		counter["component_hit"] += 1
	if kw_ok:
		counter["keyword_hit"] += 1
	if comp_ok and kw_ok:
		counter["both_hit"] += 1


def safe_rate(num: int, den: int) -> float:
	return (num / den * 100.0) if den else 0.0


def format_row(name: str, stat: Dict[str, int]) -> str:
	total = stat["total"]
	comp = stat["component_hit"]
	kw = stat["keyword_hit"]
	both = stat["both_hit"]
	return (
		f"{name:28s} | "
		f"N={total:4d} | "
		f"Comp={comp:4d} ({safe_rate(comp, total):6.2f}%) | "
		f"KW={kw:4d} ({safe_rate(kw, total):6.2f}%) | "
		f"Both={both:4d} ({safe_rate(both, total):6.2f}%)"
	)


def analyze(
	result_file: Path,
	gt_file: Path,
	component_match_mode: str,
) -> Dict[str, Any]:
	results = load_jsonl(result_file)
	gts = load_jsonl(gt_file)

	gt_by_uuid = {str(item.get("uuid", "")).strip(): item for item in gts}

	overall = init_counter()
	by_category: Dict[str, Dict[str, int]] = defaultdict(init_counter)

	missing_gt: List[str] = []

	for row in results:
		uuid = str(row.get("uuid", "")).strip()
		if not uuid:
			continue

		gt = gt_by_uuid.get(uuid)
		if gt is None:
			missing_gt.append(uuid)
			continue

		category = str(gt.get("fault_category", "unknown") or "unknown")

		comp = str(row.get("component", "") or "")
		reason = str(row.get("reason", "") or "")

		instances = as_list(gt.get("instance"))
		keywords = as_list(gt.get("key_metrics"))

		comp_ok = component_match(comp, instances, mode=component_match_mode)
		kw_ok = keyword_hit(reason, keywords)

		update_counter(overall, comp_ok, kw_ok)
		update_counter(by_category[category], comp_ok, kw_ok)

	return {
		"result_file": str(result_file),
		"overall": overall,
		"by_category": dict(sorted(by_category.items(), key=lambda x: x[0])),
		"missing_gt": missing_gt,
		"total_result_rows": len(results),
		"total_gt_rows": len(gts),
		"evaluated_rows": overall["total"],
		"component_match_mode": component_match_mode,
	}


def print_report(report: Dict[str, Any]) -> None:
	print("=" * 96)
	print("组件准确率 + 根因关键词命中率分析")
	print("=" * 96)

	print("\n[数据规模]")
	print(f"- 结果文件行数: {report['total_result_rows']}")
	print(f"- GT 文件行数: {report['total_gt_rows']}")
	print(f"- 可评估行数(按 uuid 对齐): {report['evaluated_rows']}")
	print(f"- 组件匹配模式: {report['component_match_mode']}")

	if report["missing_gt"]:
		print(f"- 结果中未在 GT 找到的 uuid 数: {len(report['missing_gt'])}")

	print("\n[整体指标]")
	print(format_row("overall", report["overall"]))

	print("\n[按 fault_category]")
	for category, stat in report["by_category"].items():
		print(format_row(category, stat))


def build_table_rows(report: Dict[str, Any]) -> List[Dict[str, Any]]:
	rows: List[Dict[str, Any]] = []
	result_file = report["result_file"]
	mode = report["component_match_mode"]

	overall = report["overall"]
	rows.append(
		{
			"result_file": result_file,
			"scope": "overall",
			"fault_category": "ALL",
			"match_mode": mode,
			"n": overall["total"],
			"component_hit": overall["component_hit"],
			"component_acc": round(safe_rate(overall["component_hit"], overall["total"]), 4),
			"keyword_hit": overall["keyword_hit"],
			"keyword_hit_rate": round(safe_rate(overall["keyword_hit"], overall["total"]), 4),
			"both_hit": overall["both_hit"],
			"both_hit_rate": round(safe_rate(overall["both_hit"], overall["total"]), 4),
		}
	)

	for category, stat in report["by_category"].items():
		rows.append(
			{
				"result_file": result_file,
				"scope": "fault_category",
				"fault_category": category,
				"match_mode": mode,
				"n": stat["total"],
				"component_hit": stat["component_hit"],
				"component_acc": round(safe_rate(stat["component_hit"], stat["total"]), 4),
				"keyword_hit": stat["keyword_hit"],
				"keyword_hit_rate": round(safe_rate(stat["keyword_hit"], stat["total"]), 4),
				"both_hit": stat["both_hit"],
				"both_hit_rate": round(safe_rate(stat["both_hit"], stat["total"]), 4),
			}
		)

	return rows


def write_total_table(rows: List[Dict[str, Any]], output_csv: Path) -> None:
	output_csv.parent.mkdir(parents=True, exist_ok=True)
	fieldnames = [
		"result_file",
		"scope",
		"fault_category",
		"match_mode",
		"n",
		"component_hit",
		"component_acc",
		"keyword_hit",
		"keyword_hit_rate",
		"both_hit",
		"both_hit_rate",
	]

	with output_csv.open("w", encoding="utf-8", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(rows)


def find_result_files(result_dir: Path) -> List[Path]:
	return sorted([p for p in result_dir.rglob("*.jsonl") if p.is_file()])


def main() -> None:
	parser = argparse.ArgumentParser(description="组件准确率与根因关键词命中率分析（批量模式）")
	parser.add_argument(
		"--result-dir",
		type=Path,
		default=Path("history_rca_result"),
		help="结果目录，递归读取其中所有 JSONL 文件",
	)
	parser.add_argument(
		"--result-file",
		type=Path,
		default=None,
		help="可选：仅分析单个结果文件（会覆盖 result-dir）",
	)
	parser.add_argument(
		"--gt-file",
		type=Path,
		default=Path("output/groundtruth.jsonl"),
		help="GT 文件(JSONL)",
	)
	parser.add_argument(
		"--component-match-mode",
		choices=["exact", "contains"],
		default="contains",
		help="组件命中判定方式：contains=包含匹配，exact=精确匹配",
	)
	parser.add_argument(
		"--output-csv",
		type=Path,
		default=Path("output/component_keyword_total_table.csv"),
		help="总表输出路径（CSV）",
	)
	parser.add_argument(
		"--print-per-file",
		action="store_true",
		help="是否打印每个结果文件的详细报告",
	)

	args = parser.parse_args()

	if not args.gt_file.exists():
		raise FileNotFoundError(f"GT 文件不存在: {args.gt_file}")

	if args.result_file is not None:
		if not args.result_file.exists():
			raise FileNotFoundError(f"结果文件不存在: {args.result_file}")
		result_files = [args.result_file]
	else:
		if not args.result_dir.exists():
			raise FileNotFoundError(f"结果目录不存在: {args.result_dir}")
		result_files = find_result_files(args.result_dir)

	if not result_files:
		raise FileNotFoundError("未找到可分析的 JSONL 结果文件")

	all_rows: List[Dict[str, Any]] = []
	failed_files: List[str] = []

	for result_file in result_files:
		try:
			report = analyze(
				result_file=result_file,
				gt_file=args.gt_file,
				component_match_mode=args.component_match_mode,
			)
			all_rows.extend(build_table_rows(report))
			if args.print_per_file:
				print("\n")
				print(f"文件: {result_file}")
				print_report(report)
		except Exception as exc:
			failed_files.append(f"{result_file}: {exc}")

	write_total_table(all_rows, args.output_csv)
	print("=" * 96)
	print("批量统计完成")
	print("=" * 96)
	print(f"结果文件数: {len(result_files)}")
	print(f"成功分析数: {len(result_files) - len(failed_files)}")
	print(f"失败数: {len(failed_files)}")
	print(f"总表输出: {args.output_csv}")

	if failed_files:
		print("\n失败文件:")
		for item in failed_files:
			print(f"- {item}")


if __name__ == "__main__":
	main()
