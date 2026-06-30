"""景点手绘缩略图路径（静态 SVG，供 P3 锚点多选展示）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

SKETCH_ROOT = Path(__file__).resolve().parent.parent.parent / "archor" / "images" / "sketches"

# 各城代表景点的定制线稿 path（viewBox 0 0 160 120）
CUSTOM_PATHS: dict[str, str] = {
    "cq_play_hongyadong": "M30,95 L35,55 L55,35 L75,50 L95,30 L115,45 L130,95 M40,95 L40,75 M100,95 L100,70",
    "cq_play_jiefangbei": "M75,25 L85,95 M55,95 L95,95 M60,40 L90,40 M65,55 L85,55",
    "cq_play_ciqikou": "M25,95 L35,60 L55,50 L80,55 L105,45 L125,60 L135,95 M45,95 L45,70 M95,95 L95,65",
    "cq_play_liziba": "M20,95 L140,95 M30,95 L30,50 L50,45 L70,50 L90,42 L110,48 L130,52 L130,95",
    "cq_play_cableway": "M25,70 L135,45 M30,95 L30,70 M120,95 L120,50",
    "cq_play_nanshan": "M20,95 L50,40 L80,55 L110,35 L140,95 M60,95 L60,75",
    "cq_play_dazu": "M40,95 L40,45 L55,35 L70,45 L70,95 M90,95 L90,40 L105,30 L120,40 L120,95",
    "cq_play_egyan": "M30,95 L45,50 L65,55 L80,40 L100,50 L115,45 L130,95",
    "bj_play_gugong": "M25,95 L35,50 L80,35 L125,50 L135,95 M50,95 L50,60 M110,95 L110,60",
    "nj_play_fuzimiao": "M30,95 L50,55 L80,45 L110,55 L130,95 M55,95 L55,70 M95,95 L95,70",
}


def _accent(poi_id: str) -> tuple[str, str]:
    h = int(hashlib.md5(poi_id.encode()).hexdigest()[:6], 16)
    hues = ["#c4a882", "#9eb4c8", "#8fa8b8", "#b45a28", "#6b9a7a", "#a08060"]
    return hues[h % len(hues)], hues[(h + 2) % len(hues)]


def sketch_svg_content(poi_id: str, name: str) -> str:
    stroke, wash = _accent(poi_id)
    path = CUSTOM_PATHS.get(poi_id, "M25,95 L45,50 L80,40 L115,50 L135,95 M55,95 L55,65 M95,95 L95,60")
    short = name[:6] if len(name) > 6 else name
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 120" role="img" aria-label="{name}">
  <rect width="160" height="120" rx="10" fill="#faf6ef"/>
  <rect x="8" y="8" width="144" height="88" rx="6" fill="{wash}" opacity="0.35"/>
  <path d="{path}" fill="none" stroke="{stroke}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M12,100 Q80,108 148,100" fill="none" stroke="{stroke}" stroke-width="1.2" opacity="0.5"/>
  <text x="80" y="112" text-anchor="middle" font-family="Georgia, serif" font-size="9" fill="#5a4632">{short}</text>
</svg>"""


def sketch_url(poi_id: str) -> str:
    return f"/archor/images/sketches/{poi_id}.svg"


def ensure_sketch_files() -> None:
    """确保种子景点均有手绘 SVG（幂等）。"""
    SKETCH_ROOT.mkdir(parents=True, exist_ok=True)
    # 从 seed 数据拉取全部景点 id + name
    try:
        from db.seed_poi_data import ATTRACTIONS
    except ImportError:
        ATTRACTIONS = []

    for row in ATTRACTIONS:
        poi_id, name = row[0], row[1]
        path = SKETCH_ROOT / f"{poi_id}.svg"
        if not path.exists():
            path.write_text(sketch_svg_content(poi_id, name), encoding="utf-8")

    for poi_id in CUSTOM_PATHS:
        if not (SKETCH_ROOT / f"{poi_id}.svg").exists():
            (SKETCH_ROOT / f"{poi_id}.svg").write_text(
                sketch_svg_content(poi_id, poi_id), encoding="utf-8"
            )
