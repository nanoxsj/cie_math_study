#!/usr/bin/env python3
"""Extract embedded worked-example images from a source PDF without screenshots."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image


def extract_page(pdf: Path, page: int, output: Path) -> None:
    prefix = output.parent / f".page-{page:02d}"
    for old in output.parent.glob(f".page-{page:02d}-*"):
        old.unlink()
    subprocess.run(
        ["pdfimages", "-png", "-f", str(page), "-l", str(page), str(pdf), str(prefix)],
        check=True,
    )
    images = sorted(output.parent.glob(f".page-{page:02d}-*.png"))
    rgb = next((path for path in images if Image.open(path).mode in {"RGB", "RGBA"}), None)
    if rgb is None:
        raise RuntimeError(f"no colour image found on PDF page {page}")
    mask = next((path for path in images if Image.open(path).mode in {"L", "LA"}), None)
    base = Image.open(rgb).convert("RGB")
    if mask is not None:
        alpha = Image.open(mask).convert("L")
        white = Image.new("RGB", base.size, "white")
        base = Image.composite(base, white, alpha)
    base.save(output, "WEBP", quality=94, method=6)
    for path in images:
        path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("pages", nargs="+", type=int)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for index, page in enumerate(args.pages, start=1):
        extract_page(args.pdf, page, args.output_dir / f"worked-example-{index:02d}.webp")


if __name__ == "__main__":
    main()
