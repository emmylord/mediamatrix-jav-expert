"""
tests/stubs/providers/base.py — MediaMatrix providers.base 的最小存根

仅供 CI 环境使用（没有真实 MediaMatrix 仓库时）。
本地开发时，MEDIAMATRIX_ROOT 指向真实仓库，此文件不会被加载。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MediaQuery:
    title: str
    media_type: str = "movie"
    year: Optional[int] = None
    extra: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    provider_id: str
    title: str
    year: Optional[int]
    media_type: str
    provider: str


@dataclass
class MediaDetail:
    provider_id: str
    title: str
    original_title: str
    year: Optional[int]
    media_type: str
    overview: str
    genres: list
    poster_url: Optional[str]
    fanart_url: Optional[str]
    logo_url: Optional[str]
    rating: Optional[float]
    provider: str
    extra: dict = field(default_factory=dict)


class BaseProvider:
    name: str = ""
    media_types: list = field(default_factory=list)
    priority: int = 10

    def search(self, query: MediaQuery) -> list[SearchResult]:
        raise NotImplementedError

    def get_detail(self, provider_id: str) -> Optional[MediaDetail]:
        raise NotImplementedError
