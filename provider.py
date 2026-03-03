"""
provider.py — JavExpertProvider

职责：
  1. 从 MediaQuery.title 提取 AV 番号（正则）
  2. 无番号时立即返回 []，不干扰普通电影刮削
  3. 调度 JavDBScraper（必须）和 DMMScraper（可选）
  4. 字段级合并：DMM 开启时以 DMM 为准，rating / genres 保留 JavDB
  5. 将合并结果封装为宿主要求的 MediaDetail
"""

import logging
import re
from typing import Optional

from providers.base import BaseProvider, MediaDetail, MediaQuery, SearchResult

from .scrapers.dmm import DMMScraper
from .scrapers.javdb import JavDBScraper

logger = logging.getLogger(__name__)

# 标准番号：字母前缀-数字，如 SSIS-001 / STARS-500 / HMN-001
# 使用 lookbehind/lookahead 代替 \b，使 _ 也能作为分隔符
# 不允许前后紧贴字母或数字，避免匹配嵌入在更长单词/数字串中的片段
_AV_CODE_RE = re.compile(r"(?i)(?<![A-Za-z0-9])([A-Z]{1,8}-\d{2,6})(?![A-Za-z0-9])")
# FC2 特殊格式（同样用 lookahead/lookbehind 代替 \b）
_FC2_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(FC2-PPV-\d{5,9})(?![A-Za-z0-9])")
# 无连字符格式：如 IPX726 → IPX-726（至少 2 字母 + 3 数字，避免匹配 H264/x265）
# 优先级最低，仅在标准格式未命中时尝试
_AV_CODE_NOHYPHEN_RE = re.compile(r"(?i)(?<![A-Za-z0-9])([A-Z]{2,8})(\d{3,6})(?![A-Za-z0-9])")

# DMM 优先覆盖的字段（rating / genres 例外，始终保留 JavDB）
_DMM_PRIORITY_FIELDS = (
    "title", "original_title", "overview",
    "poster_url", "fanart_url",
    "release_date", "year",
    "director", "studio", "label", "series", "duration",
)


class JavExpertProvider(BaseProvider):
    name = "jav_expert"
    media_types = ["movie"]
    priority = 5  # TMDB=1 之后，LLM（默认10）之前

    def __init__(self, config: dict) -> None:
        sources = config.get("sources", {})

        javdb_cfg = sources.get("javdb", {})
        self._javdb = JavDBScraper(javdb_cfg)

        dmm_cfg = sources.get("dmm", {})
        self._dmm_enabled: bool = dmm_cfg.get("enabled", False)
        self._dmm: Optional[DMMScraper] = DMMScraper(dmm_cfg) if self._dmm_enabled else None

    # ------------------------------------------------------------------
    # BaseProvider 接口
    # ------------------------------------------------------------------

    def search(self, query: MediaQuery) -> list[SearchResult]:
        """
        从文件名提取番号。
        未识别到番号时返回 []，完全不影响 TMDB 等其他 Provider。
        """
        av_code = self._extract_av_code(query.title)
        if av_code is None and query.extra.get("filename"):
            av_code = self._extract_av_code(query.extra["filename"])
            if av_code:
                logger.debug("[JavExpert] 从原始文件名提取番号: %s", av_code)
        if av_code is None:
            return []

        logger.debug("[JavExpert] 识别到番号: %s", av_code)
        return [
            SearchResult(
                provider_id=f"movie:{av_code}",
                title=av_code,
                year=query.year,
                media_type="movie",
                provider=self.name,
            )
        ]

    def get_detail(self, provider_id: str) -> Optional[MediaDetail]:
        """
        provider_id 格式：movie:{AV_CODE}
        调度爬虫、合并结果、返回 MediaDetail。
        """
        av_code = provider_id.split(":", 1)[-1].upper()

        # 必须数据源：JavDB
        javdb_data = self._javdb.search(av_code)
        if javdb_data is None:
            logger.warning("[JavExpert] JavDB 无结果: %s", av_code)
            return None

        # 可选增强：DMM
        merged = javdb_data
        if self._dmm_enabled and self._dmm:
            dmm_data = self._dmm.search(av_code)
            if dmm_data:
                merged = self._merge(javdb_data, dmm_data)
                logger.debug("[JavExpert] 已合并 DMM 数据: %s", av_code)
            else:
                logger.debug("[JavExpert] DMM 无结果，仅使用 JavDB: %s", av_code)

        detail = self._to_media_detail(merged, av_code, provider_id)
        logger.info("[JavExpert] 刮削成功: %s | 标题=%s | 来源=%s",
                    av_code, detail.title, merged.get("source", "javdb"))
        return detail

    # ------------------------------------------------------------------
    # 番号提取
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_av_code(title: str) -> Optional[str]:
        """从文件名/标题中提取番号。

        优先级：FC2 → 标准格式（含 -）→ 无连字符格式（自动补 -）
        无连字符格式（如 IPX726）只在前两者均未命中时尝试，并规范化为 IPX-726。
        """
        m = _FC2_RE.search(title)
        if m:
            return m.group(1).upper()
        m = _AV_CODE_RE.search(title)
        if m:
            return m.group(1).upper()
        m = _AV_CODE_NOHYPHEN_RE.search(title)
        if m:
            return f"{m.group(1).upper()}-{m.group(2)}"
        return None

    # ------------------------------------------------------------------
    # 字段合并
    # ------------------------------------------------------------------

    @staticmethod
    def _merge(javdb: dict, dmm: dict) -> dict:
        """
        以 JavDB 为基础，DMM 字段优先覆盖。
        rating / genres 例外：始终保留 JavDB（DMM 无社区数据）。
        actresses：DMM 为准（日文官方名），JavDB 补充缺失。
        """
        merged = dict(javdb)  # 浅拷贝，JavDB 作为基础

        for field in _DMM_PRIORITY_FIELDS:
            if dmm.get(field):
                merged[field] = dmm[field]

        # 演员：DMM 官方名优先，JavDB 作为补充
        if dmm.get("actresses"):
            merged["actresses"] = dmm["actresses"]

        # rating / genres 已随 JavDB 基础保留，不被覆盖

        merged["source"] = "javdb+dmm"
        return merged

    # ------------------------------------------------------------------
    # 结果封装
    # ------------------------------------------------------------------

    @staticmethod
    def _to_media_detail(data: dict, av_code: str, provider_id: str) -> MediaDetail:
        title = data.get("title") or av_code
        return MediaDetail(
            provider_id=provider_id,
            title=title,
            original_title=data.get("original_title") or title,
            year=data.get("year"),
            media_type="movie",
            overview=data.get("overview", ""),
            genres=data.get("genres", []),
            poster_url=data.get("poster_url"),
            fanart_url=data.get("fanart_url"),
            logo_url=None,
            rating=data.get("rating"),
            provider="jav_expert",
            extra={
                "av_code": av_code,
                "actresses": data.get("actresses", []),
                "director": data.get("director"),
                "studio": data.get("studio"),
                "label": data.get("label"),
                "series": data.get("series"),
                "duration": data.get("duration"),
                "source": data.get("source", "javdb"),
            },
        )
