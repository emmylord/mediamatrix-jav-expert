"""
scrapers/base.py — 所有 JAV 数据源爬虫的抽象基类

使用 curl_cffi 替代 httpx，通过模拟真实浏览器 TLS 指纹绕过 Cloudflare。

提供：
  - curl_cffi Session（持久连接，impersonate="chrome120"）
  - 请求限速（每次请求前固定等待）
  - 429 指数退避重试
  - 网络错误自动重试
  - 404 快速返回 None（不重试）
  - User-Agent 随机轮换
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Optional

from curl_cffi import requests as cffi_requests
from curl_cffi.requests.errors import RequestsError

logger = logging.getLogger(__name__)

_DEFAULT_UAS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class BaseJavScraper(ABC):
    """JAV 数据源爬虫基类，子类只需实现 search() 和 get_detail()。"""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._base_url: str = config.get("base_url", "")
        self._delay: float = float(config.get("delay", 2.0))
        self._max_retries: int = int(config.get("max_retries", 3))
        self._user_agents: list[str] = config.get("user_agents") or _DEFAULT_UAS
        self._client = cffi_requests.Session(
            impersonate="chrome120",
            headers={"Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7"},
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _random_ua(self) -> str:
        return random.choice(self._user_agents)

    def _get(self, url: str, params: Optional[dict] = None) -> Optional[cffi_requests.Response]:
        """
        带限速、重试、退避的 GET 请求。

        返回值：
          - Response：请求成功（2xx）
          - None：404 或超过最大重试仍无结果
        抛出：
          - RequestsError：网络错误（超过重试次数后）
          - HTTPError：非 404/429 的 HTTP 错误（超过重试次数后）
        """
        for attempt in range(1, self._max_retries + 1):
            time.sleep(self._delay)
            try:
                resp = self._client.get(
                    url,
                    params=params,
                    headers={"User-Agent": self._random_ua()},
                )
            except RequestsError as exc:
                logger.warning(
                    "请求异常 %s (attempt %d/%d): %s",
                    type(exc).__name__, attempt, self._max_retries, url,
                )
                if attempt < self._max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise

            if resp.status_code == 404:
                logger.debug("404，跳过: %s", url)
                return None

            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning(
                    "429 限速，%ds 后重试 (attempt %d/%d): %s",
                    wait, attempt, self._max_retries, url,
                )
                time.sleep(wait)
                continue

            try:
                resp.raise_for_status()
            except Exception:
                logger.warning(
                    "HTTP %d (attempt %d/%d): %s",
                    resp.status_code, attempt, self._max_retries, url,
                )
                if attempt < self._max_retries:
                    continue
                raise

            return resp

        return None

    # ------------------------------------------------------------------
    # 资源管理
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BaseJavScraper":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 子类必须实现
    # ------------------------------------------------------------------

    @abstractmethod
    def search(self, av_code: str) -> Optional[dict]:
        """搜索番号，成功返回原始元数据 dict，失败返回 None。"""
        ...

    @abstractmethod
    def get_detail(self, url: str) -> Optional[dict]:
        """抓取详情页，成功返回原始元数据 dict，失败返回 None。"""
        ...
