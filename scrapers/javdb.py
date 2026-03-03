"""
scrapers/javdb.py — JavDB 数据源爬虫

JavDB HTML 结构要点（选择器如网站改版需同步更新）：

搜索页 /search?q={番号}&f=all：
  .movie-list .item > a[href]             ← 结果链接
  .movie-list .item .video-title strong   ← 番号（用于精确匹配）

详情页 /v/{id}：
  h2.title .current-title       ← 当前语言标题
  h2.title .origin-title        ← 原始语言标题
  img.video-cover               ← 封面图
  nav.panel .panel-block        ← 各字段行（strong=标签，span.value=值）

  面板字段标签（英文）：
    ID / Released Date / Duration / Director / Maker /
    Label / Series / Tags / Actor(s) / Rating

  演员（Actor(s)）格式：<a>名字</a>♀ 或 <a>名字</a>♂
  只保留 ♀ 演员；若无性别标记则保留全部。
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from .base import BaseJavScraper

logger = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"(\d+)")
_YEAR_RE = re.compile(r"(\d{4})")
_RATING_RE = re.compile(r"([\d.]+)")


class JavDBScraper(BaseJavScraper):
    """JavDB 爬虫：搜索番号 → 定位详情页 → 解析元数据"""

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def search(self, av_code: str) -> Optional[dict]:
        """搜索番号，返回第一条精确匹配的详情数据；无结果返回 None。"""
        url = f"{self._base_url}/search"
        resp = self._get(url, params={"q": av_code, "f": "all"})
        if resp is None:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        detail_url = self._find_detail_url(soup, av_code)
        if detail_url is None:
            logger.debug("[JavDB] 搜索无精确匹配: %s", av_code)
            return None

        logger.debug("[JavDB] 找到详情页: %s → %s", av_code, detail_url)
        return self.get_detail(detail_url)

    def get_detail(self, url: str) -> Optional[dict]:
        """抓取详情页，返回元数据 dict；页面不存在返回 None。"""
        resp = self._get(url)
        if resp is None:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        result = self._parse_detail(soup, url)
        logger.info("[JavDB] 解析完成: %s | 标题=%s", url, result.get("title", ""))
        return result

    # ------------------------------------------------------------------
    # 搜索结果解析
    # ------------------------------------------------------------------

    def _find_detail_url(self, soup: BeautifulSoup, av_code: str) -> Optional[str]:
        """在搜索结果中找到番号精确匹配的详情页 URL。"""
        target = av_code.upper()
        for item in soup.select(".movie-list .item"):
            strong_el = item.select_one(".video-title strong")
            if strong_el and strong_el.get_text(strip=True).upper() == target:
                link = item.select_one("a[href]")
                if link:
                    href = link["href"]
                    return f"{self._base_url}{href}" if href.startswith("/") else href
        return None

    # ------------------------------------------------------------------
    # 详情页解析
    # ------------------------------------------------------------------

    def _parse_detail(self, soup: BeautifulSoup, url: str) -> dict:
        result: dict = {"source": "javdb", "detail_url": url}

        # 标题
        title_el = soup.select_one("h2.title .current-title")
        if title_el:
            result["title"] = title_el.get_text(strip=True)

        # 原始标题（日文）
        origin_el = soup.select_one("h2.title .origin-title")
        if origin_el:
            result["original_title"] = origin_el.get_text(strip=True)

        # 封面图
        cover_el = soup.select_one("img.video-cover")
        if cover_el:
            src = cover_el.get("src") or cover_el.get("data-src") or ""
            if src:
                url = src if src.startswith("http") else f"https:{src}"
                result["fanart_url"] = url
                # TODO: 将 fanart 横版图裁切右半边作为 poster 竖版图，
                #       目前用同一张图兜底；DMM 开启时会由 mediumUrl 覆盖为真正的竖版
                result["poster_url"] = url

        # panel-block 信息行（含评分）
        for block in soup.select(".panel-block"):
            label_el = block.select_one("strong")
            if not label_el:
                continue
            label = label_el.get_text(strip=True).rstrip(":")
            value_el = block.select_one("span.value") or block
            value = value_el.get_text(strip=True)
            self._parse_panel_field(result, label, value_el, value)

        return result

    def _parse_panel_field(
        self, result: dict, label: str, value_el, value: str
    ) -> None:
        """将 panel-block 一行解析到 result dict 对应字段。

        标签优先匹配英文（真实页面语言），同时兼容中文/繁体。
        """
        label_lower = label.lower()

        # 番号
        if label_lower == "id" or "番號" in label or "番号" in label:
            result["av_code"] = value.upper()

        # 发行日期
        elif (
            label_lower in ("released date", "release date")
            or ("日期" in label and "發行商" not in label and "发行商" not in label)
        ):
            result["release_date"] = value
            m = _YEAR_RE.search(value)
            if m:
                result["year"] = int(m.group(1))

        # 时长（分钟）
        elif label_lower == "duration" or "時長" in label or "时长" in label or "時間" in label or "时間" in label:
            m = _DURATION_RE.search(value)
            if m:
                result["duration"] = int(m.group(1))

        # 导演
        elif label_lower == "director" or "導演" in label or "导演" in label:
            result["director"] = value

        # 片商（制作公司）
        elif label_lower == "maker" or "片商" in label or "製作" in label or "制作" in label:
            result["studio"] = value

        # 发行商
        elif label_lower == "label" or "發行商" in label or "发行商" in label:
            result["label"] = value

        # 系列
        elif label_lower == "series" or "系列" in label:
            result["series"] = value

        # 类别 / 标签
        elif (
            label_lower == "tags"
            or "類別" in label or "类别" in label
            or "標籤" in label or "标签" in label
        ):
            tags = [a.get_text(strip=True) for a in value_el.select("a")]
            result["genres"] = tags if tags else ([value] if value else [])

        # 演员（只保留 ♀）
        elif (
            label_lower in ("actor(s)", "actors", "actress", "actress(es)")
            or "演員" in label or "演员" in label
        ):
            result["actresses"] = self._extract_female_actors(value_el)

        # 评分
        elif label_lower == "rating" or "評分" in label or "评分" in label:
            m = _RATING_RE.search(value)
            if m:
                result["rating"] = float(m.group(1))

    @staticmethod
    def _extract_female_actors(value_el) -> list[str]:
        """从演员列表提取女演员。

        若存在 ♀/♂ 性别标记，只保留 ♀ 演员；
        否则（无标记时）返回所有演员。
        """
        text = value_el.get_text()
        has_gender_marker = "♀" in text or "♂" in text
        if has_gender_marker:
            actresses = []
            for a in value_el.select("a"):
                name = a.get_text(strip=True)
                sibling = a.next_sibling
                if sibling and "♀" in str(sibling):
                    actresses.append(name)
            return actresses
        else:
            return [a.get_text(strip=True) for a in value_el.select("a")]
