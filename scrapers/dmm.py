"""
scrapers/dmm.py — DMM GraphQL API 客户端

DMM 已从传统 HTML 页面迁移到 video.dmm.co.jp（Next.js SPA），
数据通过 GraphQL API 提供：https://api.video.dmm.co.jp/graphql

id 格式说明（不同厂商规律不一致，按顺序尝试）：
  优先：前缀小写 + 数字补零到 5 位，如 SSIS-001 → ssis00001
  降级：前缀小写 + 原始数字，如 HPP-011 → hpp011

所需请求头：
  fanza-device: BROWSER
  origin: https://video.dmm.co.jp
  Cookie: age_check_done=1

注意：DMM 对境外 IP 可能需要代理才能访问。
"""

import logging
import re
import time
from typing import Optional

import httpx

from .base import BaseJavScraper

logger = logging.getLogger(__name__)

_AV_CODE_RE = re.compile(r"^([A-Za-z]+)-?(\d+)$")

_GRAPHQL_URL = "https://api.video.dmm.co.jp/graphql"

# 完整 GraphQL query（保留所有 fragment 以通过服务端变量校验）
_QUERY = """query ContentPageData($id: ID!, $isLoggedIn: Boolean!, $isAmateur: Boolean!, $isAnime: Boolean!, $isAv: Boolean!, $isCinema: Boolean!, $isSP: Boolean!, $shouldFetchRelatedTags: Boolean = false) {
  ppvContent(id: $id) {
    ...ContentData
    __typename
  }
  reviewSummary(contentId: $id) {
    ...ReviewSummary
    __typename
  }
  ...basketCountFragment @include(if: $isSP)
}
fragment ContentData on PPVContent {
  id
  floor
  title
  description
  packageImage { largeUrl mediumUrl __typename }
  ...AmateurAdditionalContentData @include(if: $isAmateur)
  ...AnimeAdditionalContentData @include(if: $isAnime)
  ...AvAdditionalContentData @include(if: $isAv)
  ...CinemaAdditionalContentData @include(if: $isCinema)
  __typename
}
fragment AmateurAdditionalContentData on PPVContent {
  deliveryStartDate
  duration
  maker { id name __typename }
  label { id name __typename }
  genres { id name __typename }
  makerContentId
  __typename
}
fragment AnimeAdditionalContentData on PPVContent {
  deliveryStartDate
  duration
  series { id name __typename }
  maker { id name __typename }
  label { id name __typename }
  genres { id name __typename }
  makerContentId
  __typename
}
fragment AvAdditionalContentData on PPVContent {
  deliveryStartDate
  makerReleasedAt
  duration
  actresses { id name nameRuby imageUrl __typename }
  directors { id name __typename }
  series { id name __typename }
  maker { id name __typename }
  label { id name __typename }
  genres { id name __typename }
  makerContentId
  relatedTags(limit: 16) @include(if: $shouldFetchRelatedTags) {
    ... on ContentTagGroup {
      tags { id name __typename }
      __typename
    }
    ... on ContentTag { id name __typename }
    __typename
  }
  __typename
}
fragment CinemaAdditionalContentData on PPVContent {
  deliveryStartDate
  duration
  actresses { id name nameRuby imageUrl __typename }
  directors { id name __typename }
  series { id name __typename }
  maker { id name __typename }
  label { id name __typename }
  genres { id name __typename }
  makerContentId
  __typename
}
fragment ReviewSummary on ReviewSummary {
  average
  total
  __typename
}
fragment basketCountFragment on Query {
  legacyBasket @skip(if: $isLoggedIn) {
    total __typename
  }
  __typename
}"""

_GRAPHQL_VARIABLES_BASE = {
    "isAmateur": False,
    "isAnime": False,
    "isAv": True,
    "isCinema": False,
    "isLoggedIn": False,
    "isSP": False,
    "shouldFetchRelatedTags": False,
}


class DMMScraper(BaseJavScraper):
    """
    DMM GraphQL API 客户端。

    不再依赖 HTML 爬取，直接请求 api.video.dmm.co.jp/graphql。
    注意：DMM 对境外 IP 可能有访问限制。
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        # GraphQL 用独立客户端（endpoint 与 base_url 不同）
        self._gql_client = httpx.Client(
            timeout=15.0,
            headers={
                "content-type": "application/json",
                "accept": "application/graphql-response+json, application/json",
                "fanza-device": "BROWSER",
                "origin": "https://video.dmm.co.jp",
                "referer": "https://video.dmm.co.jp/",
                "User-Agent": self._random_ua(),
            },
            cookies={"age_check_done": "1"},
        )

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def search(self, av_code: str) -> Optional[dict]:
        """根据番号查询 DMM，返回元数据 dict；找不到返回 None。"""
        m = _AV_CODE_RE.match(av_code.strip())
        if not m:
            logger.debug("[DMM] 番号格式无法转换为 id：%s", av_code)
            return None

        prefix, num = m.group(1).lower(), m.group(2)
        strategy = self._config.get("cid_strategy", "pattern_then_search")

        # 候选 id 列表
        candidates: list[str] = []
        if strategy in ("pattern", "pattern_then_search"):
            candidates.append(f"{prefix}{num.zfill(5)}")   # 优先：5位补零
            if len(num) != 5:
                candidates.append(f"{prefix}{num}")         # 降级：原始位数

        for dmm_id in candidates:
            result = self.get_detail(dmm_id)
            if result is not None:
                return result

        if strategy in ("search", "pattern_then_search"):
            logger.debug("[DMM] pattern 未命中，尝试搜索: %s", av_code)
            dmm_id = self._search_id(av_code)
            if dmm_id:
                return self.get_detail(dmm_id)

        logger.debug("[DMM] 所有策略均无结果: %s", av_code)
        return None

    def get_detail(self, dmm_id: str) -> Optional[dict]:
        """
        用 dmm_id 直接调用 GraphQL，返回元数据 dict。
        ppvContent 为 null（id 不存在）时返回 None。
        """
        time.sleep(self._delay)

        payload = {
            "operationName": "ContentPageData",
            "query": _QUERY,
            "variables": {**_GRAPHQL_VARIABLES_BASE, "id": dmm_id},
        }
        try:
            resp = self._gql_client.post(_GRAPHQL_URL, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("[DMM] GraphQL 请求失败 %d: %s", exc.response.status_code, dmm_id)
            return None
        except httpx.RequestError as exc:
            logger.warning("[DMM] 网络错误 %s: %s", type(exc).__name__, dmm_id)
            return None

        data = resp.json()
        if data.get("errors"):
            logger.debug("[DMM] GraphQL errors for %s: %s", dmm_id, data["errors"])

        content = (data.get("data") or {}).get("ppvContent")
        if not content:
            logger.debug("[DMM] ppvContent 为空: id=%s", dmm_id)
            return None

        review = (data.get("data") or {}).get("reviewSummary") or {}
        result = self._parse_graphql(content, review, dmm_id)
        logger.info("[DMM] 解析完成: id=%s | 标题=%s", dmm_id, result.get("title", ""))
        return result

    # ------------------------------------------------------------------
    # 搜索降级（从旧版搜索页提取 id）
    # ------------------------------------------------------------------

    def _search_id(self, av_code: str) -> Optional[str]:
        """
        通过 www.dmm.co.jp/search 搜索，从结果链接提取 content id。
        注意：该接口返回的 cid 格式与 GraphQL id 略有差异，仅作兜底。
        """
        url = f"https://www.dmm.co.jp/search/=/searchstr={av_code}/"
        resp = self._get(url)
        if resp is None:
            return None

        # 从链接里找 id 参数或 cid 参数
        import re as _re
        for pattern in [r'[?&]id=([^&/"]+)', r'/cid=([^/?/"]+)/']:
            m = _re.search(pattern, resp.text)
            if m:
                return m.group(1)
        return None

    # ------------------------------------------------------------------
    # GraphQL 响应解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_graphql(content: dict, review: dict, dmm_id: str) -> dict:
        """将 GraphQL ppvContent 节点转换为统一 dict 格式。"""
        pkg_img = content.get("packageImage") or {}
        poster_url = pkg_img.get("largeUrl") or pkg_img.get("mediumUrl")

        # 时长单位为秒，转换为分钟
        duration_sec = content.get("duration")
        duration_min = round(duration_sec / 60) if duration_sec else None

        release_date = content.get("makerReleasedAt") or content.get("deliveryStartDate") or ""
        year = None
        if release_date:
            m = re.search(r"(\d{4})", release_date)
            if m:
                year = int(m.group(1))
            release_date = release_date[:10].replace("/", "-")  # 统一为 YYYY-MM-DD

        return {
            "source": "dmm",
            "dmm_id": dmm_id,
            "title": content.get("title", ""),
            "original_title": content.get("title", ""),
            "overview": content.get("description", ""),
            "poster_url": poster_url,
            "fanart_url": poster_url,
            "release_date": release_date,
            "year": year,
            "duration": duration_min,
            "director": next((d["name"] for d in content.get("directors", []) if d.get("name")), None),
            "studio": (content.get("maker") or {}).get("name"),
            "label": (content.get("label") or {}).get("name"),
            "series": (content.get("series") or {}).get("name"),
            "actresses": [a["name"] for a in content.get("actresses", []) if a.get("name")],
            "genres": [g["name"] for g in content.get("genres", []) if g.get("name")],
            "rating": review.get("average"),
            "av_code": (content.get("makerContentId") or "").upper() or None,
        }

    # ------------------------------------------------------------------
    # 资源管理
    # ------------------------------------------------------------------

    def close(self) -> None:
        super().close()
        self._gql_client.close()
