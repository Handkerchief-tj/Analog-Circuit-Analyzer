from __future__ import annotations

import html
import math
import re
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import sympy as sp


def _ensure_sfg_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    candidate = project_root.parent / "ISACA-Desktop" / "src"
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


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


def _latex_inline(expr: Any) -> str:
    try:
        return f"\\({sp.latex(sp.sympify(expr))}\\)"
    except Exception:
        return f"\\({html.escape(str(expr))}\\)"


def _format_frequency(hz: float | None) -> str:
    if hz is None:
        return "-"
    hz = float(hz)
    if math.isinf(hz):
        return "∞"
    omega = 2 * math.pi * hz
    for scale, suffix in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")):
        if abs(hz) >= scale:
            return f"{hz / scale:.6g} {suffix} (ω={omega / scale:.6g} {suffix}/rad)"
    return f"{hz:.6g} Hz (ω={omega:.6g} rad/s)"


def _root_plane(value: complex | None) -> str:
    if value is None:
        return "未知"
    real = float(value.real)
    if abs(real) <= 1e-12:
        return "j轴"
    return "LHP" if real < 0 else "RHP"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join([header, separator, body])


def _parameter_summary(dominant_term_transfer: Any | None) -> str:
    if dominant_term_transfer is None:
        return "-"
    influences = list(getattr(dominant_term_transfer, "parameter_influences", ()) or ())
    if not influences:
        return "-"
    preview = []
    for item in influences[:3]:
        try:
            preview.append(f"{item.parameter} ({item.max_normalized_sensitivity:.3g})")
        except Exception:
            preview.append(str(item.parameter))
    return ", ".join(preview)


def _root_table(title: str, roots: tuple[Any, ...]) -> str:
    rows: list[list[str]] = []
    for index, root in enumerate(roots, start=1):
        expr = root.expression if getattr(root, "expression", None) is not None else getattr(root, "numeric_value", None)
        frequency = _format_frequency(getattr(root, "frequency_hz", None))
        plane = _root_plane(getattr(root, "numeric_value", None))
        rows.append([
            f"{title}{index}",
            _latex_inline(expr) if expr is not None else "-",
            frequency,
            plane,
        ])
    if not rows:
        return f"**{title}**\n\n- none"
    return f"**{title}**\n\n{_table(['根', '符号表达式', '数值频率', '半平面'], rows)}"


def _analysis_details(result: Any) -> str:
    try:
        from sfg_prototype.pipeline import (
            error_policy_report,
            error_trace_report,
            operation_ranking_report,
            subrange_simplification_report,
        )
    except Exception:
        return ""

    parts = [
        error_policy_report(result),
        subrange_simplification_report(result),
        operation_ranking_report(result),
        error_trace_report(result),
    ]
    detail_text = "\n\n".join(part for part in parts if part)
    if not detail_text.strip():
        return ""
    return f"<details><summary>算法详情/调试信息</summary><pre style='white-space:pre-wrap'>{html.escape(detail_text)}</pre></details>"


def run_sfg_symbolic_simplification(
    netlist_text: str,
    param_df_data: list[list[Any]] | None = None,
    start_f: float | None = None,
    stop_f: float | None = None,
    points: int | None = None,
    relative_error_pct: float = 5.0,
    magnitude_error_db: float = 2.0,
    phase_error_deg: float = 5.0,
    max_steps_per_subrange: int = 10,
) -> dict[str, Any]:
    _ensure_sfg_path()
    try:
        from sfg_prototype.pipeline import SimplificationConfig, simplify_netlist
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
    relative_limit = float(relative_error_pct)
    if relative_limit > 1:
        relative_limit /= 100.0
    config = SimplificationConfig(
        error_norm="hybrid_linf",
        total_error_budget=relative_limit,
        magnitude_error_db=float(magnitude_error_db),
        phase_error_deg=float(phase_error_deg),
        max_steps_per_subrange=int(max_steps_per_subrange),
    )
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

    reference = result.pipeline.reference
    reference_title = "circuit.cir"
    final_error = result.final_error
    status_text = "通过" if final_error.accepted else "未通过"
    status_class = "color:#1f7a3f;font-weight:600;" if final_error.accepted else "color:#a12622;font-weight:600;"

    parts: list[str] = []
    parts.append("## SFG 符号化简结果")
    parts.append(f"- 分析对象: `{reference_title}`")
    parts.append(f"- source: `{source}`")
    parts.append(f"- detector: `{detector}`")
    parts.append(f"- 完整参考传递函数: {_latex_inline(reference.laplace)}")
    parts.append(
        f"- 整体误差验收: <span style='{status_class}'>{status_text}</span>"
        f" (相对 {final_error.max_relative_error:.3g}, 幅值 {final_error.max_magnitude_error_db:.3g} dB, 相位 {final_error.max_phase_error_deg:.3g}°)"
    )
    parts.append(
        f"- 误差上限: 相对 {relative_limit:.3g}, 幅值 {float(magnitude_error_db):.3g} dB, 相位 {float(phase_error_deg):.3g}°"
    )

    if result.pipeline.clusters:
        rows: list[list[str]] = []
        for cluster, spec in zip(result.pipeline.clusters, result.pipeline.error_specs):
            rows.append([
                f"{cluster.index}",
                f"{_format_frequency(spec.lower_frequency_hz)}",
                "∞" if math.isinf(spec.upper_frequency_hz) else _format_frequency(spec.upper_frequency_hz),
                f"{len(cluster.roots)}",
                f"{_format_frequency(cluster.center_frequency_hz)}",
            ])
        parts.append("")
        parts.append("## 根聚类与频段划分")
        parts.append(_table(["频段", "下边界", "上边界", "根数", "中心频率"], rows))

    if result.subrange_results:
        parts.append("")
        parts.append("## 分频段结论")
        for item in result.subrange_results:
            upper = "∞" if math.isinf(item.upper_frequency_hz) else _format_frequency(item.upper_frequency_hz)
            lower = _format_frequency(item.lower_frequency_hz)
            parts.append(f"### 频段 {item.cluster_index}: {lower} - {upper}")
            if item.transfer.success:
                chosen = item.dominant_term_transfer.transfer if item.dominant_term_transfer is not None else item.transfer.transfer
                parts.append(f"- 推荐简化传递函数: {_latex_inline(chosen)}")
                parts.append(_root_table("极点", item.transfer.poles))
                parts.append("")
                parts.append(_root_table("零点", item.transfer.zeros))
                parts.append("")
                parts.append(f"- 主导元件参数: {_parameter_summary(item.dominant_term_transfer)}")
                error = item.error
                parts.append(
                    f"- 误差验收: {'通过' if error.accepted else '未通过'}"
                    f" (相对 {error.max_relative_error:.3g}, 幅值 {error.max_magnitude_error_db:.3g} dB, 相位 {error.max_phase_error_deg:.3g}°)"
                )
            else:
                parts.append(f"- 推荐简化传递函数: 失败，{html.escape(str(item.transfer.error))}")

    parts.append("")
    parts.append(_analysis_details(result))

    markdown = "\n".join(part for part in parts if part is not None)
    return {
        "ok": True,
        "error": None,
        "source": source,
        "detector": detector,
        "result": result,
        "markdown": markdown,
        "graph_html": "",
    }
