#!/usr/bin/env python3
"""Keep only SVG objects whose geometry intersects a PDF-coordinate region.

This is the object-filtering step used by the Further Mathematics diagram
workflow. It preserves vector paths and removes text/glyph objects outside
the selected diagram region; it does not rasterise or screenshot the page.
"""

from __future__ import annotations

import argparse
import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def numbers(value: str | None) -> list[float]:
    return [float(item) for item in NUMBER_RE.findall(value or "")]


def affine(transform: str | None) -> tuple[float, float, float, float, float, float]:
    if not transform:
        return 1, 0, 0, 1, 0, 0
    matrix = re.search(r"matrix\(([^)]+)\)", transform)
    if matrix:
        values = numbers(matrix.group(1))
        if len(values) >= 6:
            return tuple(values[:6])  # type: ignore[return-value]
    translate = re.search(r"translate\(([^)]+)\)", transform)
    if translate:
        values = numbers(translate.group(1))
        return 1, 0, 0, 1, values[0], values[1] if len(values) > 1 else 0
    return 1, 0, 0, 1, 0, 0


def compose(parent: tuple[float, float, float, float, float, float], child: tuple[float, float, float, float, float, float]):
    a, b, c, d, e, f = parent
    g, h, i, j, k, l = child
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    )


def apply(matrix: tuple[float, float, float, float, float, float], x: float, y: float):
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def points(element: ET.Element, inherited=(1, 0, 0, 1, 0, 0)) -> list[tuple[float, float]]:
    matrix = compose(inherited, affine(element.get("transform")))
    tag = local(element.tag)
    raw: list[tuple[float, float]] = []
    if tag in {"use", "image", "rect", "circle", "ellipse", "line", "polygon", "polyline"}:
        x = float(element.get("x", 0))
        y = float(element.get("y", 0))
        raw.append((x, y))
        if element.get("width") and element.get("height"):
            raw.append((x + float(element.get("width")), y + float(element.get("height"))))
    elif tag == "path":
        values = numbers(element.get("d"))
        raw.extend((values[index], values[index + 1]) for index in range(0, len(values) - 1, 2))
    elif tag == "text":
        raw.append((float(element.get("x", 0)), float(element.get("y", 0))))
    return [apply(matrix, x, y) for x, y in raw] + [point for child in list(element) for point in points(child, matrix)]


def intersects(element: ET.Element, box: tuple[float, float, float, float]) -> bool:
    x, y, width, height = box
    right, bottom = x + width, y + height
    # Do not add a generous margin here: glyph objects from the next line of
    # question text can otherwise bleed into the extracted diagram.
    return any(x <= px <= right and y <= py <= bottom for px, py in points(element))


def filter_element(element: ET.Element, box: tuple[float, float, float, float], inherited=(1, 0, 0, 1, 0, 0), drop_use_y: tuple[float, ...] = (), drop_use_points: tuple[tuple[float, float], ...] = ()) -> ET.Element | None:
    tag = local(element.tag)
    if tag == "defs":
        return copy.deepcopy(element)
    if tag == "use" and drop_use_y:
        try:
            if any(abs(float(element.get("y", "nan")) - target) < 0.35 for target in drop_use_y):
                return None
        except ValueError:
            pass
    if tag == "use" and drop_use_points:
        try:
            ux = float(element.get("x", "nan"))
            uy = float(element.get("y", "nan"))
            if any(abs(ux - x) < 0.35 and abs(uy - y) < 0.35 for x, y in drop_use_points):
                return None
        except ValueError:
            pass
    matrix = compose(inherited, affine(element.get("transform")))
    if tag in {"g", "svg"}:
        children = []
        for child in list(element):
            kept = filter_element(child, box, matrix, drop_use_y, drop_use_points)
            if kept is not None:
                children.append(kept)
        if not children:
            return None
        out = copy.copy(element)
        out[:] = children
        return out
    return copy.deepcopy(element) if intersects(element, box) else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--box", required=True, help="x,y,width,height in PDF points")
    parser.add_argument("--drop-use-y", action="append", type=float, default=[], help="Remove use/glyph objects at this source y-coordinate")
    parser.add_argument("--drop-use-point", action="append", default=[], help="Remove one use/glyph object at source x,y")
    args = parser.parse_args()
    box = tuple(float(item.strip()) for item in args.box.split(","))
    if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
        raise SystemExit("box must be x,y,width,height")
    drop_points = tuple(tuple(float(part) for part in item.split(",", 1)) for item in args.drop_use_point)
    tree = ET.parse(args.input)
    root = tree.getroot()
    output = ET.Element(root.tag, dict(root.attrib))
    x, y, width, height = box
    output.set("width", f"{width:g}pt")
    output.set("height", f"{height:g}pt")
    output.set("viewBox", f"{x:g} {y:g} {width:g} {height:g}")
    output.set("overflow", "hidden")
    clip_id = "diagram-clip"
    clip_path = ET.SubElement(output, f"{{{SVG}}}clipPath", {"id": clip_id})
    ET.SubElement(
        clip_path,
        f"{{{SVG}}}rect",
        {"x": f"{x:g}", "y": f"{y:g}", "width": f"{width:g}", "height": f"{height:g}"},
    )
    definitions = []
    kept_content = []
    for child in list(root):
        if local(child.tag) == "defs":
            definitions.append(copy.deepcopy(child))
            continue
        kept = filter_element(child, box, drop_use_y=tuple(args.drop_use_y), drop_use_points=drop_points)
        if kept is not None:
            kept_content.append(kept)
    for item in definitions:
        output.append(item)
    ET.SubElement(
        output,
        f"{{{SVG}}}rect",
        {"x": f"{x:g}", "y": f"{y:g}", "width": f"{width:g}", "height": f"{height:g}", "fill": "white"},
    )
    content = ET.SubElement(output, f"{{{SVG}}}g", {"clip-path": f"url(#{clip_id})"})
    content.extend(kept_content)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(output).write(args.output, encoding="UTF-8", xml_declaration=True)


if __name__ == "__main__":
    main()
