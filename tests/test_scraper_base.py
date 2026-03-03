"""
tests/test_scraper_base.py — BaseJavScraper 单元测试

覆盖：限速、429 退避、404 快速返回、网络错误重试、UA 轮换。

网络错误使用 curl_cffi.requests.errors.RequestsError（与 base.py 一致）。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from curl_cffi.requests.errors import RequestsError

from scrapers.base import BaseJavScraper


# ------------------------------------------------------------------
# 测试用的最小子类
# ------------------------------------------------------------------

class _ConcreteScaper(BaseJavScraper):
    def search(self, av_code):
        return None

    def get_detail(self, url):
        return None


def _make_scraper(delay: float = 0.0, max_retries: int = 3) -> _ConcreteScaper:
    return _ConcreteScaper({
        "base_url": "https://example.com",
        "delay": delay,
        "max_retries": max_retries,
        "user_agents": ["TestAgent/1.0"],
    })


def _mock_response(status_code: int, text: str = "") -> MagicMock:
    """构造模拟 HTTP 响应。status_code >= 400 时 raise_for_status() 抛出异常。"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ------------------------------------------------------------------
# 测试用例
# ------------------------------------------------------------------

class TestRandomUA:
    def test_returns_ua_from_list(self):
        s = _make_scraper()
        assert s._random_ua() == "TestAgent/1.0"

    def test_uses_default_ua_when_config_empty(self):
        s = _ConcreteScaper({"user_agents": []})
        # 空列表时使用模块默认 UA 列表，不应抛出
        from scrapers.base import _DEFAULT_UAS
        assert s._user_agents == _DEFAULT_UAS


class TestGetSuccess:
    @patch("scrapers.base.time.sleep")
    def test_returns_response_on_200(self, mock_sleep):
        s = _make_scraper()
        resp_200 = _mock_response(200, "<html>ok</html>")
        s._client.get = MagicMock(return_value=resp_200)

        result = s._get("https://example.com/page")

        assert result is resp_200
        mock_sleep.assert_called_once_with(0.0)  # delay=0

    @patch("scrapers.base.time.sleep")
    def test_passes_params_to_client(self, mock_sleep):
        s = _make_scraper()
        resp_200 = _mock_response(200)
        s._client.get = MagicMock(return_value=resp_200)

        s._get("https://example.com/search", params={"q": "SSIS-001"})

        call_kwargs = s._client.get.call_args
        assert call_kwargs.kwargs.get("params") == {"q": "SSIS-001"}


class TestGet404:
    @patch("scrapers.base.time.sleep")
    def test_returns_none_on_404(self, mock_sleep):
        s = _make_scraper()
        s._client.get = MagicMock(return_value=_mock_response(404))

        result = s._get("https://example.com/missing")

        assert result is None
        # 404 不重试：只请求一次，只 sleep 一次
        assert s._client.get.call_count == 1

    @patch("scrapers.base.time.sleep")
    def test_no_retry_on_404(self, mock_sleep):
        s = _make_scraper(max_retries=3)
        s._client.get = MagicMock(return_value=_mock_response(404))
        s._get("https://example.com/missing")
        assert s._client.get.call_count == 1


class TestGet429:
    @patch("scrapers.base.time.sleep")
    def test_retries_on_429_then_succeeds(self, mock_sleep):
        s = _make_scraper(max_retries=3)
        s._client.get = MagicMock(side_effect=[
            _mock_response(429),
            _mock_response(200, "ok"),
        ])

        result = s._get("https://example.com/page")

        assert result is not None
        assert s._client.get.call_count == 2

    @patch("scrapers.base.time.sleep")
    def test_exponential_backoff_on_429(self, mock_sleep):
        """429 时额外等待 2^attempt 秒"""
        s = _make_scraper(delay=0.0, max_retries=3)
        s._client.get = MagicMock(side_effect=[
            _mock_response(429),
            _mock_response(200),
        ])

        s._get("https://example.com/page")

        # sleep 调用：attempt=1 的正常 delay(0.0) + 429 backoff(2^1=2)
        calls = mock_sleep.call_args_list
        sleep_values = [c.args[0] for c in calls]
        assert 2 in sleep_values  # backoff 2^1

    @patch("scrapers.base.time.sleep")
    def test_returns_none_when_all_retries_are_429(self, mock_sleep):
        s = _make_scraper(max_retries=3)
        s._client.get = MagicMock(return_value=_mock_response(429))

        result = s._get("https://example.com/page")

        assert result is None
        assert s._client.get.call_count == 3


class TestGetNetworkError:
    @patch("scrapers.base.time.sleep")
    def test_retries_on_request_error(self, mock_sleep):
        s = _make_scraper(max_retries=3)
        s._client.get = MagicMock(side_effect=[
            RequestsError("connection refused"),
            _mock_response(200, "ok"),
        ])

        result = s._get("https://example.com/page")

        assert result is not None
        assert s._client.get.call_count == 2

    @patch("scrapers.base.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        s = _make_scraper(max_retries=2)
        s._client.get = MagicMock(
            side_effect=RequestsError("connection refused")
        )

        with pytest.raises(RequestsError):
            s._get("https://example.com/page")

        assert s._client.get.call_count == 2


class TestGetHttpError:
    @patch("scrapers.base.time.sleep")
    def test_retries_on_500(self, mock_sleep):
        s = _make_scraper(max_retries=3)
        s._client.get = MagicMock(side_effect=[
            _mock_response(500),
            _mock_response(200, "ok"),
        ])

        result = s._get("https://example.com/page")

        assert result is not None

    @patch("scrapers.base.time.sleep")
    def test_raises_http_error_after_max_retries(self, mock_sleep):
        s = _make_scraper(max_retries=2)
        s._client.get = MagicMock(return_value=_mock_response(500))

        # raise_for_status() 抛出的 Exception 在超过重试次数后传出
        with pytest.raises(Exception):
            s._get("https://example.com/page")


class TestContextManager:
    def test_close_called_on_exit(self):
        s = _make_scraper()
        s._client.close = MagicMock()
        with s:
            pass
        s._client.close.assert_called_once()
