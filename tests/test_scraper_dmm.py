"""
tests/test_scraper_dmm.py — DMMScraper 单元测试（GraphQL 版）

所有网络请求通过 mock 替代，无需真实网络连接。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.dmm import DMMScraper, _GRAPHQL_URL


# ------------------------------------------------------------------
# 工具
# ------------------------------------------------------------------

def _make_scraper(strategy: str = "pattern_then_search") -> DMMScraper:
    return DMMScraper({
        "base_url": "https://www.dmm.co.jp",
        "delay": 0.0,
        "max_retries": 3,
        "user_agents": ["TestAgent/1.0"],
        "cid_strategy": strategy,
    })


def _gql_response(content: dict | None, review: dict | None = None) -> MagicMock:
    """构造 GraphQL 成功响应 mock。"""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "data": {
            "ppvContent": content,
            "reviewSummary": review or {},
        }
    })
    return resp


def _gql_null_response() -> MagicMock:
    """ppvContent 为 null 的响应（id 不存在）。"""
    return _gql_response(None, None)


def _gql_error_response(status: int = 400) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock(status_code=status))
    )
    return resp


# ------------------------------------------------------------------
# DMM GraphQL 响应样板
# ------------------------------------------------------------------

_CONTENT_SSIS001 = {
    "id": "ssis00001",
    "floor": "av",
    "title": "一ヶ月間の禁欲の果てに",
    "description": "官方简介内容",
    "packageImage": {
        "largeUrl": "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/ssis00001/ssis00001pl.jpg",
        "mediumUrl": "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/ssis00001/ssis00001ps.jpg",
    },
    "makerReleasedAt": "2021-02-18T15:00:00Z",
    "deliveryStartDate": "2021-01-01T00:00:00Z",
    "duration": 8826,  # 秒
    "actresses": [
        {"id": "1", "name": "葵つかさ", "nameRuby": "あおいつかさ", "imageUrl": ""},
        {"id": "2", "name": "乙白さやか", "nameRuby": "おとしろさやか", "imageUrl": ""},
    ],
    "directors": [{"id": "10", "name": "苺原"}],
    "series": None,
    "maker": {"id": "100", "name": "エスワン ナンバーワンスタイル"},
    "label": {"id": "200", "name": "S1 NO.1 STYLE"},
    "genres": [
        {"id": "1", "name": "美少女"},
        {"id": "2", "name": "ハイビジョン"},
    ],
    "makerContentId": "SSIS-001",
}

_REVIEW_SSIS001 = {"average": 4.381, "total": 21}


# ------------------------------------------------------------------
# 测试：_parse_graphql
# ------------------------------------------------------------------

class TestParseGraphql:
    def setup_method(self):
        self.s = _make_scraper()
        self.result = self.s._parse_graphql(_CONTENT_SSIS001, _REVIEW_SSIS001, "ssis00001")

    def test_title(self):
        assert self.result["title"] == "一ヶ月間の禁欲の果てに"

    def test_overview(self):
        assert self.result["overview"] == "官方简介内容"

    def test_poster_url(self):
        assert "ssis00001ps.jpg" in self.result["poster_url"]

    def test_fanart_url(self):
        assert "ssis00001pl.jpg" in self.result["fanart_url"]

    def test_poster_and_fanart_are_different(self):
        assert self.result["poster_url"] != self.result["fanart_url"]

    def test_duration_converted_to_minutes(self):
        # 8826 秒 → 147 分钟
        assert self.result["duration"] == 147

    def test_release_date(self):
        assert self.result["release_date"] == "2021-02-18"

    def test_year(self):
        assert self.result["year"] == 2021

    def test_studio(self):
        assert self.result["studio"] == "エスワン ナンバーワンスタイル"

    def test_label(self):
        assert self.result["label"] == "S1 NO.1 STYLE"

    def test_director(self):
        assert self.result["director"] == "苺原"

    def test_actresses(self):
        assert self.result["actresses"] == ["葵つかさ", "乙白さやか"]

    def test_genres(self):
        assert self.result["genres"] == ["美少女", "ハイビジョン"]

    def test_rating(self):
        assert self.result["rating"] == pytest.approx(4.381)

    def test_av_code_from_maker_content_id(self):
        assert self.result["av_code"] == "SSIS-001"

    def test_series_none(self):
        assert self.result["series"] is None

    def test_source(self):
        assert self.result["source"] == "dmm"

    def test_no_duration_when_missing(self):
        content = {**_CONTENT_SSIS001, "duration": None}
        result = self.s._parse_graphql(content, {}, "ssis00001")
        assert result["duration"] is None


# ------------------------------------------------------------------
# 测试：get_detail()
# ------------------------------------------------------------------

class TestGetDetail:
    @patch("scrapers.dmm.time.sleep")
    def test_returns_dict_on_success(self, mock_sleep):
        s = _make_scraper()
        s._gql_client.post = MagicMock(
            return_value=_gql_response(_CONTENT_SSIS001, _REVIEW_SSIS001)
        )
        result = s.get_detail("ssis00001")
        assert result is not None
        assert result["title"] == "一ヶ月間の禁欲の果てに"

    @patch("scrapers.dmm.time.sleep")
    def test_returns_none_when_ppvcontent_null(self, mock_sleep):
        s = _make_scraper()
        s._gql_client.post = MagicMock(return_value=_gql_null_response())
        result = s.get_detail("ssis00001")
        assert result is None

    @patch("scrapers.dmm.time.sleep")
    def test_returns_none_on_http_error(self, mock_sleep):
        s = _make_scraper()
        s._gql_client.post = MagicMock(return_value=_gql_error_response(400))
        result = s.get_detail("ssis00001")
        assert result is None

    @patch("scrapers.dmm.time.sleep")
    def test_returns_none_on_network_error(self, mock_sleep):
        s = _make_scraper()
        s._gql_client.post = MagicMock(side_effect=httpx.ConnectError("refused"))
        result = s.get_detail("ssis00001")
        assert result is None

    @patch("scrapers.dmm.time.sleep")
    def test_passes_correct_id_to_graphql(self, mock_sleep):
        s = _make_scraper()
        s._gql_client.post = MagicMock(
            return_value=_gql_response(_CONTENT_SSIS001, _REVIEW_SSIS001)
        )
        s.get_detail("ssis00001")
        payload = s._gql_client.post.call_args.kwargs["json"]
        assert payload["variables"]["id"] == "ssis00001"


# ------------------------------------------------------------------
# 测试：search() — pattern 策略
# ------------------------------------------------------------------

class TestSearchPattern:
    @patch("scrapers.dmm.time.sleep")
    def test_tries_5digit_first(self, mock_sleep):
        s = _make_scraper(strategy="pattern")
        s._gql_client.post = MagicMock(
            return_value=_gql_response(_CONTENT_SSIS001, _REVIEW_SSIS001)
        )
        result = s.search("SSIS-001")
        assert result is not None
        # 第一次调用的 id 应该是 5 位
        payload = s._gql_client.post.call_args_list[0].kwargs["json"]
        assert payload["variables"]["id"] == "ssis00001"

    @patch("scrapers.dmm.time.sleep")
    def test_falls_back_to_original_digits(self, mock_sleep):
        """5 位补零无结果时，尝试原始位数。"""
        s = _make_scraper(strategy="pattern")
        s._gql_client.post = MagicMock(side_effect=[
            _gql_null_response(),   # ssis00001 → null
            _gql_response(_CONTENT_SSIS001, _REVIEW_SSIS001),  # ssis001 → 命中
        ])
        result = s.search("SSIS-001")
        assert result is not None
        second_payload = s._gql_client.post.call_args_list[1].kwargs["json"]
        assert second_payload["variables"]["id"] == "ssis001"

    @patch("scrapers.dmm.time.sleep")
    def test_returns_none_when_pattern_fails(self, mock_sleep):
        s = _make_scraper(strategy="pattern")
        s._gql_client.post = MagicMock(return_value=_gql_null_response())
        result = s.search("SSIS-001")
        assert result is None

    @patch("scrapers.dmm.time.sleep")
    def test_invalid_av_code_skipped(self, mock_sleep):
        s = _make_scraper()
        s._gql_client.post = MagicMock()
        result = s.search("Inception 2010")
        assert result is None
        s._gql_client.post.assert_not_called()


# ------------------------------------------------------------------
# 测试：search() — pattern_then_search 降级
# ------------------------------------------------------------------

class TestSearchPatternThenSearch:
    @patch("scrapers.base.time.sleep")   # _get 里的 sleep
    @patch("scrapers.dmm.time.sleep")    # get_detail 里的 sleep
    def test_falls_back_to_search_when_pattern_fails(self, mock_dmm_sleep, mock_base_sleep):
        s = _make_scraper(strategy="pattern_then_search")
        # pattern 两次都 null
        s._gql_client.post = MagicMock(side_effect=[
            _gql_null_response(),   # ssis00001
            _gql_null_response(),   # ssis001
            _gql_response(_CONTENT_SSIS001, _REVIEW_SSIS001),  # 搜索后命中
        ])
        # 模拟搜索页返回含 id 的链接
        search_html = '<a href="?id=ssis00001">SSIS-001</a>'
        mock_http_resp = MagicMock(spec=httpx.Response)
        mock_http_resp.status_code = 200
        mock_http_resp.text = search_html
        mock_http_resp.raise_for_status = MagicMock()
        s._client.get = MagicMock(return_value=mock_http_resp)

        result = s.search("SSIS-001")
        assert result is not None

    @patch("scrapers.dmm.time.sleep")
    def test_returns_none_when_both_fail(self, mock_sleep):
        s = _make_scraper(strategy="pattern_then_search")
        s._gql_client.post = MagicMock(return_value=_gql_null_response())
        # 搜索页也无结果
        mock_http_resp = MagicMock(spec=httpx.Response)
        mock_http_resp.status_code = 200
        mock_http_resp.text = "<html>no results</html>"
        mock_http_resp.raise_for_status = MagicMock()
        s._client.get = MagicMock(return_value=mock_http_resp)

        result = s.search("SSIS-001")
        assert result is None


# ------------------------------------------------------------------
# 测试：资源管理
# ------------------------------------------------------------------

class TestClose:
    def test_both_clients_closed(self):
        s = _make_scraper()
        s._client.close = MagicMock()
        s._gql_client.close = MagicMock()
        s.close()
        s._client.close.assert_called_once()
        s._gql_client.close.assert_called_once()
