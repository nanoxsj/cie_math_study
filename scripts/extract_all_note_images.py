#!/usr/bin/env python3
"""Extract every unique embedded colour image from a PDF, compositing its mask."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = Path("/private/tmp") / f"embedded-{hashlib.sha1(str(args.pdf).encode()).hexdigest()[:10]}"
    for old in prefix.parent.glob(prefix.name + "-*.png"):
        old.unlink()
    subprocess.run(["pdfimages", "-png", str(args.pdf), str(prefix)], check=True)
    pngs = sorted(prefix.parent.glob(prefix.name + "-*.png"))
    seen: set[str] = set()
    index = 0
    for colour in pngs:
        image = Image.open(colour)
        if image.mode == "L":
            continue
        suffix = colour.stem.rsplit("-", 1)[-1]
        mask = prefix.parent / f"{prefix.name}-{int(suffix)+1:03d}.png"
        base = image.convert("RGB")
        if mask.exists() and Image.open(mask).mode in {"L", "LA"}:
            base = Image.composite(base, Image.new("RGB", base.size, "white"), Image.open(mask).convert("L"))
        digest = hashlib.sha1(base.tobytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        index += 1
        output = args.output_dir / f"worked-example-{index:02d}.webp"
        base.save(output, "WEBP", quality=94, method=6)
    for path in pngs:
        path.unlink()
    print(f"extracted {index} unique embedded images")


if __name__ == "__main__":
    main()
