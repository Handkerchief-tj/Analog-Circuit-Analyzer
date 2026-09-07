from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEVICE_PINS: dict[str, list[str]] = {
    "R": ["1", "2"],
    "C": ["1", "2"],
    "L": ["1", "2"],
    "V": ["p", "n"],
    "I": ["p", "n"],
    "G": ["1", "2", "3", "4"],
    "E": ["1", "2", "3", "4"],
    "F": ["1", "2", "3", "4"],
    "H": ["1", "2", "3", "4"],
    "M": ["D", "G", "S", "B"],
    "QV": ["C", "B", "E", "S"],
    "GROUND": ["0"],
    "PORT": ["p"],
}

SYMBOL_TO_DEVICE = {
    "R": "R",
    "C": "C",
    "L": "L",
    "V": "V",
    "I": "I",
    "VCCS": "G",
    "VCVS": "E",
    "CCCS": "F",
    "CCVS": "H",
    "M": "M",
    "QV": "QV",
    "0": "GROUND",
    "port": "PORT",
}


@dataclass
class Point:
    x: float
    y: float


@dataclass
class PinRef:
    component_id: str
    pin_id: str


@dataclass
class Component:
    id: str
    refdes: str
    device: str
    position: Point
    rotation: int = 0
    model: str | None = None
    parameters: dict[str, str] = field(default_factory=dict)
    control_ref: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Wire:
    id: str
    source: PinRef
    target: PinRef
    waypoints: list[Point] = field(default_factory=list)
    net_name: str | None = None


@dataclass
class AnalysisPorts:
    source: str | None = None
    detector: str | None = None
    lgref: str | None = None


@dataclass
class SchematicDocument:
    title: str = "Web Schematic"
    components: list[Component] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    parameters: dict[str, str] = field(default_factory=dict)
    analysis: AnalysisPorts = field(default_factory=AnalysisPorts)


def _pin_list(device: str) -> list[str]:
    return DEVICE_PINS.get(device, ["1", "2"])


def _pin_positions(device: str) -> dict[str, tuple[float, float]]:
    pins = _pin_list(device)
    if len(pins) == 1:
        return {pins[0]: (0.0, 0.0)}
    if len(pins) == 2:
        return {pins[0]: (-28.0, 0.0), pins[1]: (28.0, 0.0)}
    return {
        pins[0]: (-28.0, -18.0),
        pins[1]: (28.0, -18.0),
        pins[2]: (-28.0, 18.0),
        pins[3]: (28.0, 18.0),
    }


def _default_analysis_name(value: str) -> str:
    if value.startswith("V_"):
        return value
    return f"V_{value}"


def default_schematic_document() -> SchematicDocument:
    return SchematicDocument(
        title="Web Schematic",
        components=[
            Component(id="V1", refdes="V1", device="V", position=Point(70, 110), parameters={"value": "1"}),
            Component(id="R1", refdes="R1", device="R", position=Point(190, 110), parameters={"value": "1k"}),
            Component(id="GND", refdes="GND", device="GROUND", position=Point(310, 110), properties={"name": "0"}),
            Component(id="OUT", refdes="OUT", device="PORT", position=Point(310, 40), properties={"name": "out"}),
        ],
        wires=[
            Wire(id="W1", source=PinRef("V1", "p"), target=PinRef("R1", "1")),
            Wire(id="W2", source=PinRef("V1", "n"), target=PinRef("GND", "0")),
            Wire(id="W3", source=PinRef("R1", "2"), target=PinRef("OUT", "p")),
        ],
        analysis=AnalysisPorts(source="V1", detector="V_out"),
    )


def document_to_tables(document: SchematicDocument) -> tuple[list[list[Any]], list[list[Any]]]:
    component_rows: list[list[Any]] = []
    wire_rows: list[list[Any]] = []
    for component in document.components:
        component_rows.append([
            component.id,
            component.refdes,
            component.device,
            component.position.x,
            component.position.y,
            component.rotation,
            component.model or "",
            _stringify_mapping(component.parameters),
            component.control_ref or "",
            str(component.properties.get("name", "")),
        ])
    for wire in document.wires:
        wire_rows.append([
            wire.id,
            wire.source.component_id,
            wire.source.pin_id,
            wire.target.component_id,
            wire.target.pin_id,
            wire.net_name or "",
            _stringify_points([[point.x, point.y] for point in wire.waypoints]),
        ])
    return component_rows, wire_rows


def document_from_tables(
    component_rows: list[list[Any]] | None,
    wire_rows: list[list[Any]] | None,
    title: str | None = None,
    source: str | None = None,
    detector: str | None = None,
) -> tuple[SchematicDocument | None, list[str]]:
    errors: list[str] = []
    components: list[Component] = []
    seen_ids: set[str] = set()
    for row in component_rows or []:
        if not row or not str(row[0]).strip():
            continue
        component_id = str(row[0]).strip()
        if component_id in seen_ids:
            errors.append(f"重复元件 ID: {component_id}")
            continue
        seen_ids.add(component_id)
        refdes = str(row[1]).strip() if len(row) > 1 and row[1] is not None else component_id
        device = str(row[2]).strip() if len(row) > 2 and row[2] is not None else "R"
        if device not in DEVICE_PINS:
            errors.append(f"不支持的元件类型: {device} ({component_id})")
            continue
        try:
            x = float(row[3]) if len(row) > 3 and str(row[3]).strip() != "" else 0.0
            y = float(row[4]) if len(row) > 4 and str(row[4]).strip() != "" else 0.0
            rotation = int(float(row[5])) if len(row) > 5 and str(row[5]).strip() != "" else 0
        except ValueError as exc:
            errors.append(f"元件 {component_id} 坐标/旋转无效: {exc}")
            continue
        model = str(row[6]).strip() if len(row) > 6 and row[6] is not None and str(row[6]).strip() else None
        parameters = _split_mapping(row[7] if len(row) > 7 else None)
        control_ref = str(row[8]).strip() if len(row) > 8 and row[8] is not None and str(row[8]).strip() else None
        name = str(row[9]).strip() if len(row) > 9 and row[9] is not None else ""
        properties: dict[str, Any] = {}
        if device in {"GROUND", "PORT"} and name:
            properties["name"] = name
        components.append(
            Component(
                id=component_id,
                refdes=refdes,
                device=device,
                position=Point(x=x, y=y),
                rotation=rotation,
                model=model,
                parameters=parameters if device not in {"GROUND", "PORT"} else {},
                control_ref=control_ref,
                properties=properties,
            )
        )
    component_map = {component.id: component for component in components}
    wires: list[Wire] = []
    for row in wire_rows or []:
        if not row or not str(row[0]).strip():
            continue
        wire_id = str(row[0]).strip()
        source_component_id = str(row[1]).strip() if len(row) > 1 else ""
        source_pin = str(row[2]).strip() if len(row) > 2 else ""
        target_component_id = str(row[3]).strip() if len(row) > 3 else ""
        target_pin = str(row[4]).strip() if len(row) > 4 else ""
        if source_component_id not in component_map or target_component_id not in component_map:
            errors.append(f"连线 {wire_id} 关联了不存在的元件")
            continue
        if not source_pin or not target_pin:
            errors.append(f"连线 {wire_id} 缺少引脚名")
            continue
        net_name = str(row[5]).strip() if len(row) > 5 and row[5] is not None else ""
        wires.append(
            Wire(
                id=wire_id,
                source=PinRef(component_id=source_component_id, pin_id=source_pin),
                target=PinRef(component_id=target_component_id, pin_id=target_pin),
                waypoints=[Point(x=p[0], y=p[1]) for p in _split_points(row[6] if len(row) > 6 else None)],
                net_name=net_name or None,
            )
        )
    if not components:
        return None, ["原理图中没有可用元件。"]
    return SchematicDocument(
        title=title or "Web Schematic",
        components=components,
        wires=wires,
        analysis=AnalysisPorts(source=source, detector=detector),
    ), errors


def import_slicap_schematic_text(text: str) -> tuple[SchematicDocument | None, list[str]]:
    try:
        raw = json.loads(text)
    except Exception as exc:
        return None, [f"SLiCAP 原理图不是合法 JSON: {exc}"]

    try:
        components: list[Component] = []
        for native in raw.get("components", []):
            symbol = str(native.get("symbol_name", ""))
            device = SYMBOL_TO_DEVICE.get(symbol)
            if device is None:
                continue
            component_id = str(native.get("instance_id", symbol or device))
            params = {str(k): str(v) for k, v in native.get("params", {}).items()}
            properties: dict[str, Any] = {}
            if device in {"GROUND", "PORT"}:
                properties["name"] = params.get("name", "0" if device == "GROUND" else component_id)
            components.append(
                Component(
                    id=component_id,
                    refdes=component_id,
                    device=device,
                    position=Point(float(native.get("x", 0.0)), float(native.get("y", 0.0))),
                    rotation=int(float(native.get("rotation", 0))) % 360,
                    model=str(native.get("model", "")) or None,
                    parameters={} if device in {"GROUND", "PORT"} else params,
                    control_ref=(native.get("refs") or [None])[0],
                    properties=properties,
                )
            )

        wires: list[Wire] = []
        for index, native_wire in enumerate(raw.get("wires", []), start=1):
            points = native_wire.get("points", [])
            if len(points) < 2:
                continue
            source_component_id, source_pin = _nearest_pin(components, points[0])
            target_component_id, target_pin = _nearest_pin(components, points[-1])
            wires.append(
                Wire(
                    id=f"W{index}",
                    source=PinRef(source_component_id, source_pin),
                    target=PinRef(target_component_id, target_pin),
                    waypoints=[Point(float(pt[0]), float(pt[1])) for pt in points[1:-1]],
                    net_name=str(native_wire.get("net_name", "")) or None,
                )
            )

        properties = raw.get("properties", {})
        title = str(properties.get("title") or "Web Schematic")
        source = None
        detector = None
        analysis_items = raw.get("analysis_items", [])
        if analysis_items:
            first = analysis_items[0]
            source_items = first.get("source", [])
            detector_items = first.get("detector", [])
            if source_items:
                source = str(source_items[0])
            if detector_items:
                kind, ref = detector_items[0]
                detector = f"{kind}_{ref}"
        return SchematicDocument(title=title, components=components, wires=wires, analysis=AnalysisPorts(source=source, detector=detector)), []
    except Exception as exc:
        return None, [f"无法解析 SLiCAP 原理图: {exc}"]


def export_netlist_from_document(document: SchematicDocument) -> tuple[str | None, list[str]]:
    try:
        netlist, diagnostics = schematic_to_netlist(document)
    except Exception as exc:
        return None, [f"原理图导出网表失败: {exc}"]
    return netlist, diagnostics


def render_document_svg(document: SchematicDocument | None) -> str:
    if document is None or not document.components:
        return ""
    bounds = [component.position for component in document.components]
    min_x = min(point.x for point in bounds) - 90
    min_y = min(point.y for point in bounds) - 90
    max_x = max(point.x for point in bounds) + 130
    max_y = max(point.y for point in bounds) + 110
    width = max(420, int(max_x - min_x))
    height = max(260, int(max_y - min_y))
    pin_positions = _absolute_pin_positions(document)

    def esc(value: Any) -> str:
        return html.escape(str(value))

    svg = [
        f"<svg class='schematic-preview' viewBox='{min_x} {min_y} {width} {height}' xmlns='http://www.w3.org/2000/svg'>",
        "<style>.schematic-preview{background:#fff;border:1px solid #d5dde2}.wire{stroke:#334155;stroke-width:2;fill:none}.comp{fill:#f8fafc;stroke:#64748b;stroke-width:1.2}.label{font:12px Segoe UI,Microsoft YaHei,sans-serif;fill:#111827}.pin{fill:#fff;stroke:#334155;stroke-width:1}</style>",
    ]
    for wire in document.wires:
        src = pin_positions.get((wire.source.component_id, wire.source.pin_id))
        dst = pin_positions.get((wire.target.component_id, wire.target.pin_id))
        if src and dst:
            svg.append(f"<line class='wire' x1='{src[0]}' y1='{src[1]}' x2='{dst[0]}' y2='{dst[1]}' />")
    for component in document.components:
        x = component.position.x
        y = component.position.y
        svg.append(f"<rect class='comp' x='{x - 34}' y='{y - 18}' width='68' height='36' rx='4' ry='4'/>")
        svg.append(f"<text class='label' x='{x}' y='{y - 6}' text-anchor='middle'>{esc(component.refdes)}</text>")
        svg.append(f"<text class='label' x='{x}' y='{y + 10}' text-anchor='middle'>{esc(component.device)}</text>")
        for pin_name, pin in _pin_positions(component.device).items():
            pin_x = x + pin[0]
            pin_y = y + pin[1]
            svg.append(f"<circle class='pin' cx='{pin_x}' cy='{pin_y}' r='2.8'/>")
            svg.append(f"<text class='label' x='{pin_x + 4}' y='{pin_y - 4}'>{esc(pin_name)}</text>")
    svg.append("</svg>")
    return "<div style='overflow:auto;max-width:100%'>" + "".join(svg) + "</div>"


def catalog_markdown() -> str:
    lines = ["| Device | Pins |", "|---|---|"]
    for device in ["R", "C", "L", "V", "I", "G", "E", "F", "H", "M", "QV", "GROUND", "PORT"]:
        lines.append(f"| `{device}` | `{', '.join(_pin_list(device))}` |")
    return "\n".join(lines)


def _stringify_mapping(mapping: dict[str, str]) -> str:
    return json.dumps(mapping, ensure_ascii=False, sort_keys=True)


def _stringify_points(points: list[list[float]]) -> str:
    return json.dumps(points, ensure_ascii=False)


def _split_mapping(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    text = str(text).strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
    except Exception:
        pass
    result: dict[str, str] = {}
    for token in re.split(r"[;,\n]", text):
        token = token.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value
    return result


def _split_points(text: str | None) -> list[list[float]]:
    if not text:
        return []
    text = str(text).strip()
    if not text:
        return []
    try:
        value = json.loads(text)
        if isinstance(value, list):
            points: list[list[float]] = []
            for item in value:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    points.append([float(item[0]), float(item[1])])
            return points
    except Exception:
        pass
    points: list[list[float]] = []
    for token in re.split(r"[;\n]", text):
        token = token.strip()
        if not token:
            continue
        pair = re.split(r"\s*,\s*|\s+", token)
        if len(pair) >= 2:
            try:
                points.append([float(pair[0]), float(pair[1])])
            except ValueError:
                continue
    return points


def _nearest_pin(components: list[Component], point: list[Any]) -> tuple[str, str]:
    x = float(point[0])
    y = float(point[1])
    best: tuple[float, str, str] | None = None
    for component in components:
        for pin_name, (dx, dy) in _pin_positions(component.device).items():
            distance = math.hypot(component.position.x + dx - x, component.position.y + dy - y)
            candidate = (distance, component.id, pin_name)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        return "", ""
    return best[1], best[2]


def _absolute_pin_positions(document: SchematicDocument) -> dict[tuple[str, str], tuple[float, float]]:
    positions: dict[tuple[str, str], tuple[float, float]] = {}
    for component in document.components:
        for pin_name, (dx, dy) in _pin_positions(component.device).items():
            positions[(component.id, pin_name)] = (component.position.x + dx, component.position.y + dy)
    return positions


def _resolve_net_names(document: SchematicDocument) -> dict[tuple[str, str], str]:
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(item: tuple[str, str]) -> tuple[str, str]:
        parent.setdefault(item, item)
        if parent[item] != item:
            parent[item] = find(parent[item])
        return parent[item]

    def union(left: tuple[str, str], right: tuple[str, str]) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for component in document.components:
        for pin in _pin_list(component.device):
            parent.setdefault((component.id, pin), (component.id, pin))
    for wire in document.wires:
        union((wire.source.component_id, wire.source.pin_id), (wire.target.component_id, wire.target.pin_id))

    groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for item in parent:
        groups.setdefault(find(item), []).append(item)

    named_roots: dict[tuple[str, str], set[str]] = {}
    for component in document.components:
        if component.device == "GROUND":
            named_roots.setdefault(find((component.id, _pin_list(component.device)[0])), set()).add("0")
        if component.device == "PORT":
            name = str(component.properties.get("name", component.refdes)).strip()
            if name:
                named_roots.setdefault(find((component.id, _pin_list(component.device)[0])), set()).add(name)
    for wire in document.wires:
        if wire.net_name:
            named_roots.setdefault(find((wire.source.component_id, wire.source.pin_id)), set()).add(wire.net_name)

    resolved: dict[tuple[str, str], str] = {}
    auto_index = 1
    for root, members in sorted(groups.items(), key=lambda item: item[1][0]):
        names = named_roots.get(root, set())
        if "0" in names:
            name = "0"
        elif names:
            name = sorted(names)[0]
        else:
            name = f"N{auto_index:03d}"
            auto_index += 1
        for member in members:
            resolved[member] = name
    return resolved


def schematic_to_netlist(document: SchematicDocument) -> tuple[str, list[str]]:
    nets = _resolve_net_names(document)
    diagnostics: list[str] = []
    lines = [f'"{document.title}"' if " " in document.title else document.title, ""]
    for component in document.components:
        if component.device in {"GROUND", "PORT"}:
            continue
        pins = _pin_list(component.device)
        nodes = [nets.get((component.id, pin), "?") for pin in pins]
        if component.device in {"R", "C", "L", "V", "I"}:
            value = component.parameters.get("value", "1")
            lines.append(f"{component.refdes} {nodes[0]} {nodes[1]} {component.device} value={value}")
        elif component.device in {"G", "E"}:
            value = component.parameters.get("value", component.parameters.get("gm", "1"))
            lines.append(f"{component.refdes} {nodes[0]} {nodes[1]} {nodes[2]} {nodes[3]} {component.device} value={value}")
        elif component.device in {"F", "H"}:
            control = component.control_ref or "?"
            value = component.parameters.get("value", component.parameters.get("gain", "1"))
            lines.append(f"{component.refdes} {nodes[0]} {nodes[1]} {nodes[2]} {nodes[3]} {control} {component.device} value={value}")
        elif component.device == "M":
            params = " ".join(f"{key}={value}" for key, value in component.parameters.items())
            lines.append(f"{component.refdes} {nodes[0]} {nodes[1]} {nodes[2]} {nodes[3]} M {params}".strip())
        elif component.device == "QV":
            params = " ".join(f"{key}={value}" for key, value in component.parameters.items())
            lines.append(f"{component.refdes} {nodes[0]} {nodes[1]} {nodes[2]} {nodes[3]} QV {params}".strip())
        else:
            diagnostics.append(f"未支持的器件类型: {component.device}")
    if document.parameters:
        lines.append("")
        lines.append(".param " + " ".join(f"{name}={value}" for name, value in sorted(document.parameters.items())))
    if document.analysis.source:
        lines.append(f".source {document.analysis.source}")
    if document.analysis.detector:
        lines.append(f".detector {document.analysis.detector}")
    lines.append(".end")
    return "\n".join(lines), diagnostics
