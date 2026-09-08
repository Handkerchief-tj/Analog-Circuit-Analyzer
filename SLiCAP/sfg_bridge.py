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
    for scale, suffix, omega_suffix in (
        (1e9, "GHz", "Grad/s"),
        (1e6, "MHz", "Mrad/s"),
        (1e3, "kHz", "krad/s"),
    ):
        if abs(hz) >= scale:
            return f"{hz / scale:.6g} {suffix} (ω={omega / scale:.6g} {omega_suffix})"
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


def _target_root_table(roots: tuple[Any, ...]) -> str:
    rows: list[list[str]] = []
    for index, root in enumerate(roots, start=1):
        kind = "极点" if getattr(root, "kind", "") == "pole" else "零点"
        expression = getattr(root, "expression", None)
        reference_value = getattr(root, "reference_value", None)
        numeric_value = getattr(root, "numeric_value", None)
        deviation = getattr(root, "relative_root_error", None)
        status = "已解析" if getattr(root, "status", "") == "resolved" else "未解析"
        rows.append([
            f"{kind}{getattr(root, 'root_index', index)}",
            _latex_inline(expression) if expression is not None else "-",
            _format_frequency(getattr(root, "reference_frequency_hz", None)),
            _format_frequency(getattr(root, "frequency_hz", None)),
            _root_plane(reference_value if reference_value is not None else numeric_value),
            status,
            "-" if deviation is None else f"{100 * float(deviation):.4g}%",
        ])
    if not rows:
        return "**本频段目标零极点**\n\n- 本频段没有闭环目标根。"
    return "**本频段目标零极点**\n\n" + _table(
        ["目标根", "符号表达式", "精确数值频率", "符号式求值频率", "半平面", "状态", "根位置偏差（诊断）"],
        rows,
    )


def _selected_subrange_error(item: Any) -> Any:
    dominant = getattr(item, "dominant_term_transfer", None)
    return dominant.nominal_error if dominant is not None else item.error


def _passes_bode_limits(error: Any, magnitude_limit_db: float, phase_limit_deg: float) -> bool:
    return (
        float(error.max_magnitude_error_db) <= magnitude_limit_db
        and float(error.max_phase_error_deg) <= phase_limit_deg
    )


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
    magnitude_error_db: float = 2.0,
    phase_error_deg: float = 5.0,
    max_steps_per_subrange: int = 10,
) -> dict[str, Any]:
    try:
        magnitude_limit = float(magnitude_error_db)
        phase_limit = float(phase_error_deg)
    except (TypeError, ValueError):
        magnitude_limit = math.nan
        phase_limit = math.nan
    if not math.isfinite(magnitude_limit) or magnitude_limit < 0:
        return {
            "ok": False,
            "error": "幅值误差上限必须是非负有限数值。",
            "markdown": "⚠️ 幅值误差上限必须是非负有限数值。",
            "graph_html": "",
        }
    if not math.isfinite(phase_limit) or phase_limit < 0:
        return {
            "ok": False,
            "error": "相位误差上限必须是非负有限数值。",
            "markdown": "⚠️ 相位误差上限必须是非负有限数值。",
            "graph_html": "",
        }

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
    config = SimplificationConfig(
        error_norm="bode_linf",
        magnitude_error_db=magnitude_limit,
        phase_error_deg=phase_limit,
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
    selected_errors = [_selected_subrange_error(item) for item in result.subrange_results if item.transfer.success]
    all_subranges_succeeded = bool(result.subrange_results) and all(item.transfer.success for item in result.subrange_results)
    overall_accepted = all_subranges_succeeded and all(
        _passes_bode_limits(error, magnitude_limit, phase_limit) for error in selected_errors
    )
    max_magnitude_error = max((float(error.max_magnitude_error_db) for error in selected_errors), default=math.inf)
    max_phase_error = max((float(error.max_phase_error_deg) for error in selected_errors), default=math.inf)
    status_text = "通过" if overall_accepted else "未通过"
    status_class = "color:#1f7a3f;font-weight:600;" if overall_accepted else "color:#a12622;font-weight:600;"

    parts: list[str] = []
    parts.append("## SFG 符号化简结果")
    parts.append(f"- 分析对象: `{reference_title}`")
    parts.append(f"- source: `{source}`")
    parts.append(f"- detector: `{detector}`")
    parts.append(f"- 完整参考传递函数: {_latex_inline(reference.laplace)}")
    parts.append(
        f"- 整体误差验收: <span style='{status_class}'>{status_text}</span>"
        f" (最大幅值 {max_magnitude_error:.3g} dB, 最大相位 {max_phase_error:.3g}°)"
    )
    parts.append(
        f"- 误差上限: 幅值 {magnitude_limit:.3g} dB, 相位 {phase_limit:.3g}°"
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
                dominant = item.dominant_term_transfer
                chosen = dominant.transfer if dominant is not None else item.transfer.transfer
                error = _selected_subrange_error(item)
                parts.append(f"- 推荐简化传递函数: {_latex_inline(chosen)}")
                parts.append(_target_root_table(tuple(item.target_root_approximations)))
                parts.append("")
                parts.append(
                    "- 说明: 根位置偏差仅用于诊断符号近似；频段是否通过只由推荐传递函数的整体幅值和相位误差决定。"
                )
                parts.append(f"- 主导元件参数: {_parameter_summary(dominant)}")
                parts.append(
                    f"- 误差验收: {'通过' if _passes_bode_limits(error, magnitude_limit, phase_limit) else '未通过'}"
                    f" (幅值 {error.max_magnitude_error_db:.3g} dB, 相位 {error.max_phase_error_deg:.3g}°)"
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
