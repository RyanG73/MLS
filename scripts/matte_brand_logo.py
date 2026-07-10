#!/usr/bin/env python3
"""Matte a flat-color logo (navy-on-near-white, no alpha) to a clean transparent PNG.

Used to produce webapp/assets/branding/{entenser-wordmark,entenser-icon,favicon}.png
from the source art in docs/logo1.PNG (wordmark) and docs/logo2.PNG (icon).

Why not a hard threshold: the source PNGs are flat vector-style art (solid navy
foreground, solid near-white background, ~254 not pure 255 due to compression noise)
but the edges are anti-aliased -- roughly 1% of pixels are a genuine blend between
the two flat colors. A single hard cutoff (e.g. "alpha=0 if all channels >= 245 else
opaque") either leaves a light halo around the artwork or produces jagged, non-
anti-aliased edges, because it collapses the blend band to a single 0/1 step instead
of the smooth ramp the original anti-aliasing implies.

What this script does instead:
  1. Solve per-pixel alpha via least-squares projection onto the bg->fg color axis
     (using the two known flat colors), not an arbitrary single-channel threshold.
     This reconstructs the smooth alpha ramp the original anti-aliasing intended.
  2. Un-premultiply: recover the true foreground color at each edge pixel via
     fg = bg + (pixel - bg) / alpha, so partially-transparent edge pixels don't
     keep a whitish/gray tint blended in from the background. Skipping this step
     causes a visible light fringe/halo when the result is composited onto a
     dark background, even though flat-region alpha and color both look correct
     in isolation.

Usage:
    python3 scripts/matte_brand_logo.py docs/logo1.PNG webapp/assets/branding/entenser-wordmark.png
    python3 scripts/matte_brand_logo.py docs/logo2.PNG webapp/assets/branding/entenser-icon.png
    python3 scripts/matte_brand_logo.py docs/logo2.PNG webapp/assets/branding/favicon.png --resize 64 64

Requires: Pillow, numpy.
"""
import argparse

import numpy as np
from PIL import Image

# Sampled from the actual source art (docs/logo1.PNG, docs/logo2.PNG): a near-white
# background (not pure 255, due to compression noise) and the flat navy foreground.
# Both source images share these colors; pass --bg/--fg to override for other art.
DEFAULT_BG = (254.0, 254.0, 254.0)
DEFAULT_FG = (7.0, 30.0, 46.0)


def matte(src, dst, bg=DEFAULT_BG, fg=DEFAULT_FG, resize=None, recolor=None):
    im = Image.open(src).convert("RGB")
    arr = np.array(im).astype(np.float32)

    bg = np.array(bg, dtype=np.float32)
    fg = np.array(fg, dtype=np.float32)
    diff = fg - bg
    denom = np.dot(diff, diff)

    # Every pixel is assumed to be a linear blend: pixel = alpha*fg + (1-alpha)*bg.
    # Solve for alpha per-pixel via least-squares projection onto the bg->fg axis
    # (uses all 3 channels, more robust than thresholding a single channel).
    pix_minus_bg = arr - bg
    alpha = np.tensordot(pix_minus_bg, diff, axes=([2], [0])) / denom
    alpha = np.clip(alpha, 0.0, 1.0)

    # Un-premultiply using the SOLVED alpha so color and alpha stay self-consistent:
    # recovered_fg = bg + (pixel - bg) / alpha, clipped and guarded against alpha~0.
    a3 = alpha[:, :, None]
    safe_a = np.clip(a3, 1e-3, 1.0)
    recovered_fg = bg + (arr - bg) / safe_a
    recovered_fg = np.clip(recovered_fg, 0, 255)
    # Where alpha is ~0 (fully transparent), color is visually irrelevant; fall back
    # to the flat fg color rather than amplified noise.
    out_rgb = np.where(a3 > 0.02, recovered_fg, fg)

    # Optional flat recolor: the shape (alpha) is already solved, so a light-on-dark
    # variant is just the same alpha with every pixel's RGB set to the target color
    # (the dark-theme webapp needs light art — the source navy vanishes on near-black).
    if recolor is not None:
        out_rgb = np.broadcast_to(np.array(recolor, dtype=np.float32), out_rgb.shape).copy()

    alpha_255 = np.clip(alpha * 255.0, 0, 255)
    out_arr = np.dstack([out_rgb, alpha_255]).astype(np.uint8)
    out = Image.fromarray(out_arr, mode="RGBA")
    if resize:
        out = out.resize(resize, Image.LANCZOS)
    out.save(dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="Source PNG (flat RGB, near-white background, no alpha)")
    ap.add_argument("dst", help="Destination RGBA PNG path")
    ap.add_argument("--bg", nargs=3, type=float, default=None, metavar=("R", "G", "B"),
                     help="Background color to matte out (default: sampled Entenser logo bg)")
    ap.add_argument("--fg", nargs=3, type=float, default=None, metavar=("R", "G", "B"),
                     help="Foreground flat color (default: sampled Entenser logo navy)")
    ap.add_argument("--resize", nargs=2, type=int, default=None, metavar=("W", "H"),
                     help="Resize output to WxH (e.g. --resize 64 64 for a favicon)")
    ap.add_argument("--recolor", nargs=3, type=float, default=None, metavar=("R", "G", "B"),
                     help="Flat-recolor the matted art (e.g. --recolor 227 233 228 for a light-on-dark variant)")
    args = ap.parse_args()

    bg = tuple(args.bg) if args.bg else DEFAULT_BG
    fg = tuple(args.fg) if args.fg else DEFAULT_FG
    resize = tuple(args.resize) if args.resize else None
    recolor = tuple(args.recolor) if args.recolor else None

    matte(args.src, args.dst, bg=bg, fg=fg, resize=resize, recolor=recolor)

    im = Image.open(args.dst)
    alpha = im.split()[-1]
    print(f"{args.dst}: {im.size} {im.mode} alpha min/max: {alpha.getextrema()}")


if __name__ == "__main__":
    main()
