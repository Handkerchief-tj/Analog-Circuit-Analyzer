from __future__ import annotations

import os
import re
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any


def _ensure_sfg_path() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    candidate = project_root.parent / "ISACA-Desktop" / "src"
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
    return candidate


def _extract_analysis_ports(netlist_text: str) -> tuple[str | None, str | None]:
    source_match = re.search(r"(?im)^\s*\.source\s+(\S+)", netlist_text)
    detector_match = re.search(r"(?im)^\s*\.detector\s+(\S+)", netlist_text)
    source = source_match.group(1).strip() if source_match else None
    detector = detector_match.group(1).strip() if detector_match else None
    return source, detector


def _build_substitutions(param_df_data: list[list[Any]] | None) -> dict[str, Any]:
    substitutions: dict[str, Any] = {}
    for row in param_df_data or []:
        if not row:
            continue
        name = str(row[0]).strip() if len(row) > 0 and row[0] is not None else ""
        value = row[1] if len(row) > 1 else None
        if name and value not in (None, ""):
            substitutions[name] = value
    return substitutions


def _graphviz_svg(dot_source: str) -> str:
    try:
        from graphviz import Source
    except Exception:
        return ""
    try:
        return Source(dot_source).pipe(format="svg").decode("utf-8")
    except Exception:
        return ""


def run_sfg_symbolic_simplification(
    netlist_text: str,
    param_df_data: list[list[Any]] | None = None,
    start_f: float | None = None,
    stop_f: float | None = None,
    points: int | None = None,
) -> dict[str, Any]:
    _ensure_sfg_path()
    try:
        from sfg_prototype.pipeline import (
            SimplificationConfig,
            error_policy_report,
            error_trace_report,
            operation_ranking_report,
            simplification_report,
            simplify_netlist,
            subrange_simplification_report,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"无法加载 ISACA Desktop 的 SFG 算法：{exc}",
            "markdown": f"⚠️ 无法加载 SFG 算法：{exc}",
            "graph_html": "",
        }

    source, detector = _extract_analysis_ports(netlist_text)
    if not source or not detector:
        return {
            "ok": False,
            "error": "网表中缺少 .source 或 .detector 指令，无法执行 SFG 符号化简。",
            "markdown": "⚠️ 网表中缺少 `.source` 或 `.detector`，无法执行 SFG 符号化简。",
            "graph_html": "",
        }

    substitutions = _build_substitutions(param_df_data)
    config = SimplificationConfig()
    if start_f is not None and stop_f is not None:
        try:
            config = replace(config, frequency_range_hz=(float(start_f), float(stop_f)))
        except Exception:
            pass
    if points is not None:
        try:
            config = replace(config, points_per_subrange=max(4, int(points)))
        except Exception:
            pass

    with tempfile.TemporaryDirectory(prefix="analog-sfg-") as tmpdir:
        netlist_path = Path(tmpdir) / "circuit.cir"
        netlist_path.write_text(netlist_text, encoding="utf-8")
        try:
            result = simplify_netlist(
                str(netlist_path),
                config=config,
                substitutions=substitutions,
                source=source,
                detector=detector,
            )
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "markdown": f"⚠️ SFG 符号化简失败：{exc}",
                "graph_html": "",
            }

    summary = simplification_report(result)
    subrange = subrange_simplification_report(result)
    ranking = operation_ranking_report(result)
    trace = error_trace_report(result)
    policy = error_policy_report(result)

    original_dot = ""
    final_dot = ""
    try:
        original_dot = result.pipeline.graph.to_dot()
    except Exception:
        original_dot = ""
    try:
        final_dot = result.final_graph.to_dot()
    except Exception:
        final_dot = ""

    graph_html = ""
    if original_dot or final_dot:
        original_svg = _graphviz_svg(original_dot) if original_dot else ""
        final_svg = _graphviz_svg(final_dot) if final_dot else ""
        if original_svg or final_svg:
            graph_html = "<div style='display:grid;gap:16px'>"
            if original_svg:
                graph_html += "<details open><summary>原始 SFG</summary>" + original_svg + "</details>"
            if final_svg:
                graph_html += "<details><summary>简化后 SFG</summary>" + final_svg + "</details>"
            graph_html += "</div>"

    markdown = "\n\n".join([
        "## SFG 符号化简",
        f"- source: `{source}`",
        f"- detector: `{detector}`",
        f"- 频率范围: `{start_f}` Hz -> `{stop_f}` Hz" if start_f is not None and stop_f is not None else "- 频率范围: 未指定",
        "### 误差策略",
        policy,
        "### 总体报告",
        summary,
        "### 分频段报告",
        subrange,
        "### 操作排序",
        ranking,
        "### 误差追踪",
        trace,
    ])

    return {
        "ok": True,
        "error": None,
        "source": source,
        "detector": detector,
        "result": result,
        "markdown": markdown,
        "graph_html": graph_html,
    }
