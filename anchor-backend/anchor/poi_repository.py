"""POI 数据库查询（供推荐与对话使用）。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "anchor.db"


@dataclass
class Attraction:
    id: str
    name: str
    city: str
    rating: float
    attract_tier: str
    attract_time: float
    longitude: float
    latitude: float
    open_time: str = ""
    ticket_price: str = ""
    brief_intro: str = ""


@dataclass
class Hotel:
    id: str
    name: str
    city: str
    rating: float
    star_level: str = ""
    price_range: str = ""
    address: str = ""


@dataclass
class Restaurant:
    id: str
    name: str
    city: str
    rating: float
    cuisine_type: str = ""
    price_range: str = ""
    address: str = ""


def _connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"数据库不存在: {path}，请先运行 python db/init_db.py")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_attractions_by_city(
    city: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    limit: int = 10,
) -> list[Attraction]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, name, city, rating, attract_tier, attract_time,
                   open_time, ticket_price, brief_intro, longitude, latitude
            FROM attractions
            WHERE city = ?
            ORDER BY rating DESC
            LIMIT ?
            """,
            (city, limit),
        ).fetchall()
        return [
            Attraction(
                id=r["id"],
                name=r["name"],
                city=r["city"],
                rating=float(r["rating"] or 0),
                attract_tier=r["attract_tier"] or "中级",
                attract_time=float(r["attract_time"] or 2),
                longitude=float(r["longitude"] or 0),
                latitude=float(r["latitude"] or 0),
                open_time=str(r["open_time"] or ""),
                ticket_price=str(r["ticket_price"] or ""),
                brief_intro=str(r["brief_intro"] or ""),
            )
            for r in rows
        ]
    finally:
        conn.close()


def get_route_chains(
    city: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    max_hops: int = 4,
) -> list[str]:
    """按 traffic_segment 拼出顺路链文案。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT ts.from_poi_id, ts.to_poi_id,
                   COALESCE(a1.name, h1.name, r1.name) AS from_name,
                   COALESCE(a2.name, h2.name, r2.name) AS to_name
            FROM traffic_segment ts
            LEFT JOIN attractions a1 ON a1.id = ts.from_poi_id
            LEFT JOIN hotels h1 ON h1.id = ts.from_poi_id
            LEFT JOIN restaurants r1 ON r1.id = ts.from_poi_id
            LEFT JOIN attractions a2 ON a2.id = ts.to_poi_id
            LEFT JOIN hotels h2 ON h2.id = ts.to_poi_id
            LEFT JOIN restaurants r2 ON r2.id = ts.to_poi_id
            WHERE ts.city = ? AND ts.from_poi_type = 'play' AND ts.to_poi_type = 'play'
            ORDER BY ts.tran_time ASC
            LIMIT ?
            """,
            (city, max_hops),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    chains: list[str] = []
    used: set[str] = set()
    for r in rows:
        from_name, to_name = r["from_name"], r["to_name"]
        if not from_name or not to_name:
            continue
        key = f"{from_name}->{to_name}"
        if key in used:
            continue
        used.add(key)
        chains.append(f"{from_name} → {to_name}")
    return chains


def get_hotels_by_city(
    city: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    limit: int = 10,
) -> list[Hotel]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, name, city, rating, star_level, price_range, address
            FROM hotels
            WHERE city = ?
            ORDER BY rating DESC
            LIMIT ?
            """,
            (city, limit),
        ).fetchall()
        return [
            Hotel(
                id=r["id"],
                name=r["name"],
                city=r["city"],
                rating=float(r["rating"] or 0),
                star_level=str(r["star_level"] or ""),
                price_range=str(r["price_range"] or ""),
                address=str(r["address"] or ""),
            )
            for r in rows
        ]
    finally:
        conn.close()


def get_restaurants_by_city(
    city: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    limit: int = 10,
) -> list[Restaurant]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, name, city, rating, cuisine_type, price_range, address
            FROM restaurants
            WHERE city = ?
            ORDER BY rating DESC
            LIMIT ?
            """,
            (city, limit),
        ).fetchall()
        return [
            Restaurant(
                id=r["id"],
                name=r["name"],
                city=r["city"],
                rating=float(r["rating"] or 0),
                cuisine_type=str(r["cuisine_type"] or ""),
                price_range=str(r["price_range"] or ""),
                address=str(r["address"] or ""),
            )
            for r in rows
        ]
    finally:
        conn.close()


def get_matching_tag(user_tag: str, attract_tier: str, *, db_path: Path | str = DEFAULT_DB_PATH) -> float:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT matching_tag FROM map_user_tag_matching
            WHERE user_tag = ? AND attract_tier = ?
            """,
            (user_tag, attract_tier),
        ).fetchone()
        return float(row["matching_tag"]) if row else 1.0
    finally:
        conn.close()


def poi_counts(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, int]:
    conn = _connect(db_path)
    try:
        out: dict[str, int] = {}
        for table in ("attractions", "hotels", "restaurants", "traffic_segment"):
            out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return out
    finally:
        conn.close()
