"""Offline result tabs for numeric and SFG analyses."""

from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QTabWidget, QVBoxLayout, QWidget

_STYLE = """
body { font-family: "Segoe UI", sans-serif; margin: 18px 24px; color: #20252a; }
h1 { color: #174f74; font-size: 22px; margin: 0 0 14px; }
h2 { color: #174f74; font-size: 17px; border-bottom: 1px solid #b9c7d0; padding-bottom: 4px; }
h3 { font-size: 14px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 18px; }
th, td { border: 1px solid #c9d2d8; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #e9f0f4; color: #173f59; }
code, pre { font-family: Consolas, monospace; }
pre { background: #f4f5f6; border: 1px solid #d8dcdf; padding: 10px; overflow-x: auto; }
.formula { overflow-x: auto; margin: 8px 0 16px; font-size: 1.08em; }
.warning { color: #8a5a00; }
.error { color: #a12622; font-weight: 600; }
.muted { color: #66727a; }
.artifact { margin: 12px 0; }
img { max-width: 100%; height: auto; border: 1px solid #d8dcdf; background: white; }
"""


def _document(title: str, body: str) -> str:
    """Wrap trusted, locally generated result markup in a consistent page."""

    resources = Path(__file__).parent / "resources" / "katex"
    css_url = (resources / "katex.min.css").resolve().as_uri()
    js_url = (resources / "katex.min.js").resolve().as_uri()
    renderer = """<script>
    document.querySelectorAll('[data-tex]').forEach(function(node) {
      if (typeof katex !== 'undefined') {
        katex.render(node.dataset.tex, node, {displayMode:true, throwOnError:false, trust:false});
      }
    });</script>"""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<link rel='stylesheet' href='{css_url}'><script src='{js_url}'></script>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><h1>{html.escape(title)}</h1>{body}{renderer}</body></html>"
    )


def _formula(value: Any, latex: str | None = None) -> str:
    """Display worker-generated TeX, with an escaped plain-text fallback."""

    if value is None:
        return "<span class='muted'>not available</span>"
    text = html.escape(str(value))
    if latex is not None:
        return f"<div class='formula' data-tex='{html.escape(latex, quote=True)}'>{text}</div>"
    return f"<pre>{text}</pre>"


def _field_formula(record: dict, field: str) -> str:
    """Read a formula from the structured worker contract without parsing SymPy."""
    return _formula(record.get(field), record.get("_latex", {}).get(field))


def _display(value: Any) -> str:
    """Use scientific notation for measured values, preserving symbolic strings."""
    if isinstance(value, float):
        return f"{value:.6e}"
    return str(value)


def _rows(headers: list[str], rows: list[list[Any]]) -> str:
    """Build a compact HTML table from already structured values."""

    header = "".join(f"<th>{html.escape(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(_display(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def _matrix_table(value: Any) -> str:
    """Render a serialized symbolic matrix without evaluating it."""

    if not isinstance(value, list) or not value:
        return "<p class='muted'>not available</p>"
    if not isinstance(value[0], list):
        value = [[item] for item in value]
    width = max(len(row) for row in value)
    return _rows([str(index + 1) for index in range(width)], value)


def _summary_html(result: dict[str, Any]) -> str:
    circuit = result.get("circuit", {})
    flattened = result.get("flattened_circuit", {})
    diagnostics = result.get("diagnostics", [])
    body = "<h2>输入与软件</h2>"
    body += _rows(
        ["项目", "值"],
        [
            ["SLiCAP", result.get("software", {}).get("slicap", "-")],
            ["标题", circuit.get("title", "-")],
            ["Source", flattened.get("source", "-")],
            ["Detector", flattened.get("detector", "-")],
            ["节点数", len(flattened.get("nodes", []))],
            ["展平元件数", len(flattened.get("elements", {}))],
        ],
    )
    body += "<h2>参数来源</h2>"
    body += _rows(
        ["参数", "表达式", "数值", "来源"],
        [
            [item.get("name", ""), item.get("expression", ""), item.get("numeric_value", ""), item.get("source", "")]
            for item in circuit.get("parameters", [])
        ],
    )
    body += "<h2>诊断</h2>"
    if diagnostics:
        body += "<ul>" + "".join(
            f"<li class='{html.escape(str(item.get('level', '')))}'>"
            f"{html.escape(str(item.get('code', 'diagnostic')))}: "
            f"{html.escape(str(item.get('message', '')))}</li>"
            for item in diagnostics
        ) + "</ul>"
    else:
        body += "<p>未发现阻断性诊断。</p>"
    return _document("分析摘要", body)


def _numeric_html(result: dict[str, Any]) -> str:
    analyses = result.get("analyses", {})
    laplace = analyses.get("laplace", {})
    pz = analyses.get("pz", {})
    body = "<h2>拉普拉斯传递函数</h2>" + _field_formula(laplace, "laplace")
    body += "<h2>直流增益</h2>" + _field_formula(pz if "DCvalue" in pz else laplace, "DCvalue")
    body += "<h2>极点</h2>" + _rows(["序号", "根 (rad/s)"], [
        [index, value] for index, value in enumerate(pz.get("poles", []), start=1)
    ])
    body += "<h2>零点</h2>" + _rows(["序号", "根 (rad/s)"], [
        [index, value] for index, value in enumerate(pz.get("zeros", []), start=1)
    ])
    bode = analyses.get("bode", {})
    artifact = bode.get("artifact")
    if artifact and Path(artifact).is_file():
        body += "<h2>波特图</h2>"
        body += f"<div class='artifact'><img src='{Path(artifact).resolve().as_uri()}'></div>"
    return _document("数值分析", body)


def _elements_html(result: dict[str, Any]) -> str:
    """Show the flattened small-signal elements and their parameter expressions."""
    elements = result.get("flattened_circuit", {}).get("elements", {})
    body = _rows(["元件", "模型", "节点（保持引脚顺序）", "参数"], [
        [name, item.get("model"), ", ".join(item.get("nodes", [])),
         "; ".join(f"{key}={value}" for key, value in item.get("params", {}).items())]
        for name, item in elements.items()
    ])
    return _document("展平后的小信号元件", body)


def _noise_html(result: dict[str, Any]) -> str:
    """Display noise spectra only when that analysis was explicitly requested."""
    noise = result.get("analyses", {}).get("noise", {})
    if not noise:
        return _document("噪声分析", "<p>本次任务未执行噪声分析。</p>")
    body = "<h2>输出噪声谱</h2>" + _field_formula(noise, "onoise")
    body += "<h2>输入等效噪声谱</h2>" + _field_formula(noise, "inoise")
    for name in ("onoiseTerms", "inoiseTerms"):
        body += f"<h2>{name}</h2>" + _rows(["来源", "表达式"], list(noise.get(name, {}).items()))
    return _document("噪声分析", body)


def _matrix_html(result: dict[str, Any]) -> str:
    matrix = result.get("analyses", {}).get("matrix") or result.get("analyses", {}).get("laplace", {})
    body = "<h2>MNA 系统矩阵 M</h2>" + _matrix_table(matrix.get("M"))
    body += "<h2>独立变量向量 Iv</h2>" + _matrix_table(matrix.get("Iv"))
    body += "<h2>未知量向量 Dv</h2>" + _matrix_table(matrix.get("Dv"))
    return _document("MNA 矩阵", body)


def _symbolic_html(result: dict[str, Any]) -> str:
    symbolic = result.get("analyses", {}).get("symbolic", {})
    body = _rows(
        ["项目", "数量"],
        [
            ["频率子区间", symbolic.get("subranges", 0)],
            ["接受的化简操作", symbolic.get("accepted_steps", 0)],
            ["拒绝的候选操作", symbolic.get("rejected_steps", 0)],
        ],
    )
    body += "<p>以下传递函数由各频段的化简子图求得。局部根解释是另一个近似层级；"
    body += "根误差与子图频响误差分别列出，不能相互替代。完整操作记录见“生成文件”。</p>"
    for item in symbolic.get("frequency_results", []):
        body += f"<h2>Cluster {item['cluster_index']}: {item['lower_frequency_hz']:.6e}–{item['upper_frequency_hz']:.6e} Hz</h2>"
        transfer = item.get("transfer", {})
        if not transfer.get("success", True):
            body += "<p class='error'>" + html.escape(str(transfer.get("error"))) + "</p>"
        else:
            body += "<h3>化简子图传递函数</h3>" + _field_formula(transfer, "transfer")
            for kind, title in (("poles", "子图极点"), ("zeros", "子图零点")):
                body += f"<details><summary>{title}</summary>"
                for root in transfer.get(kind, []):
                    body += _field_formula(root, "expression")
                body += "</details>"
        body += "<h3>相对于原始电路的本频段误差</h3>"
        error = item.get("error", {})
        body += _rows(["幅值误差 (dB)", "相位误差 (deg)", "相对误差"], [[
            error.get("max_magnitude_error_db"), error.get("max_phase_error_deg"), error.get("max_relative_error"),
        ]])
        dominant = item.get("dominant_term_transfer")
        if dominant:
            body += "<h3>经独立误差检查的主导项传递函数</h3>" + _field_formula(dominant, "transfer")
            body += _rows(["原始项数", "保留项数", "幅值误差 (dB)", "相位误差 (deg)"], [[
                dominant.get("full_term_count"), dominant.get("retained_term_count"),
                dominant.get("error", {}).get("max_magnitude_error_db"),
                dominant.get("error", {}).get("max_phase_error_deg"),
            ]])
            body += _rows(["保留参数", "最大归一化灵敏度", "峰值频率 (Hz)"], [[
                value.get("parameter"), value.get("max_normalized_sensitivity"), value.get("peak_frequency_hz"),
            ] for value in dominant.get("parameter_influences", [])])
        body += "<h3>目标根的物理符号解释</h3>"
        for root in item.get("target_roots", []):
            if root.get("status") != "resolved":
                body += "<p class='error'>此局部根表达式尚未通过根误差验收，以下仅为候选，不是已接受的最终根。</p>"
            body += _rows(["类别", "类型", "频率 (Hz)", "相对根误差", "状态", "位置", "主导参数"], [[
                root.get("category"), root.get("kind"), root.get("frequency_hz"), root.get("relative_root_error"),
                root.get("status"), root.get("location"), ", ".join(root.get("parameters", [])),
            ]])
            body += _field_formula(root, "expression")
    svg_paths = [
        Path(path) for name, path in result.get("artifacts", {}).items()
        if str(name).lower().endswith(".svg") and str(name).lower().startswith("sfg_")
    ]
    if svg_paths:
        body += "<h2>信号流图</h2>"
        for path in svg_paths:
            if path.is_file():
                body += f"<h3>{html.escape(path.name)}</h3><img src='{path.resolve().as_uri()}'>"
    if not symbolic:
        body += "<p class='muted'>本次任务未执行 SFG 符号化简。</p>"
    return _document("SFG 分频段符号结果", body)


class _LocalPage(QWebEnginePage):
    """Do not navigate from a result document to remote or executable URLs."""

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return url.isLocalFile() or url.scheme() == "about"


class _HtmlView(QWebEngineView):
    """QWebEngine page restricted to local generated content and files."""

    def __init__(self):
        super().__init__()
        self._temporary = tempfile.TemporaryDirectory(prefix="isaca-result-")
        self.setPage(_LocalPage(self))
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)

    def set_document(self, markup: str, base_path: Path | None = None) -> None:
        # File-backed pages avoid Qt's 2 MB setHtml/data-URL limit for large circuits.
        document = Path(self._temporary.name) / "result.html"
        document.write_text(markup, encoding="utf-8")
        self.setUrl(QUrl.fromLocalFile(str(document)))


class ResultTabs(QTabWidget):
    """Display one completed worker result without parsing SLiCAP HTML."""

    artifact_open_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        self._views = [_HtmlView() for _ in range(6)]
        for view, title in zip(self._views, ("摘要", "小信号元件", "数值结果", "MNA", "噪声", "SFG 符号结果")):
            self.addTab(view, title)
        artifacts_page = QWidget()
        layout = QVBoxLayout(artifacts_page)
        self.artifact_list = QListWidget()
        self.artifact_list.itemDoubleClicked.connect(self._open_artifact)
        layout.addWidget(self.artifact_list)
        self.addTab(artifacts_page, "生成文件")

    def show_result(self, result: dict[str, Any]) -> None:
        """Replace every tab from one structured worker result."""

        artifacts = result.get("artifacts", {})
        base = Path(next(iter(artifacts.values()))).parent if artifacts else Path.cwd()
        pages = (
            _summary_html(result),
            _elements_html(result),
            _numeric_html(result),
            _matrix_html(result),
            _noise_html(result),
            _symbolic_html(result),
        )
        for view, page in zip(self._views, pages):
            view.set_document(page, base)
        self.artifact_list.clear()
        for name, raw_path in sorted(artifacts.items()):
            item = QListWidgetItem(f"{name}\n{raw_path}")
            item.setData(256, str(raw_path))
            self.artifact_list.addItem(item)
        self.setCurrentIndex(0)

    def _open_artifact(self, item: QListWidgetItem) -> None:
        path = Path(str(item.data(256)))
        if not path.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.artifact_open_failed.emit(f"无法打开生成文件：{path}")


def result_snapshot(result: dict[str, Any]) -> str:
    """Return deterministic JSON for tests and support diagnostics."""

    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
