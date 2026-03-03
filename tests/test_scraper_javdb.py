"""
tests/test_scraper_javdb.py — JavDBScraper 单元测试

所有 HTTP 请求均通过 mock 替代，无需实际网络连接。

HTML 样板基于真实 JavDB 页面结构（2024年底版本）：
  - 搜索：番号在 .video-title strong
  - 详情：封面用 img.video-cover，标签为英文，演员含 ♀/♂ 标记
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.javdb import JavDBScraper


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------

def _make_scraper() -> JavDBScraper:
    return JavDBScraper({
        "base_url": "https://javdb.com",
        "delay": 0.0,
        "max_retries": 3,
        "user_agents": ["TestAgent/1.0"],
    })


def _mock_resp(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


# ------------------------------------------------------------------
# 搜索页 HTML 样板（.video-title strong 含番号）
# ------------------------------------------------------------------

_SEARCH_HTML_HIT = """
<div class="movie-list">
  <div class="item">
    <a class="box" href="/v/BmVw7">
      <div class="video-title">
        <strong>SSIS-001</strong>
        <span class="other-title">某某标题</span>
      </div>
    </a>
  </div>
  <div class="item">
    <a class="box" href="/v/Other1">
      <div class="video-title">
        <strong>SSIS-002</strong>
      </div>
    </a>
  </div>
</div>
"""

_SEARCH_HTML_NO_MATCH = """
<div class="movie-list">
  <div class="item">
    <a class="box" href="/v/Other1">
      <div class="video-title">
        <strong>SSIS-002</strong>
      </div>
    </a>
  </div>
</div>
"""

# ------------------------------------------------------------------
# 详情页 HTML 样板（真实英文标签 + 演员性别标记）
# ------------------------------------------------------------------

_DETAIL_HTML = """
<h2 class="title">
  <strong class="current-title">某某标题</strong>
  <small class="origin-title">某某タイトル</small>
</h2>
<img class="video-cover" src="https://pics.example.com/cover.jpg" />
<nav class="panel">
  <div class="panel-block">
    <strong>ID:</strong>
    <span class="value">
      <a href="/search?q=SSIS&amp;f=all">SSIS</a><a href="/search?q=SSIS-001&amp;f=all">-001</a>
    </span>
  </div>
  <div class="panel-block">
    <strong>Released Date:</strong>
    <span class="value">2021-01-15</span>
  </div>
  <div class="panel-block">
    <strong>Duration:</strong>
    <span class="value">120 minute(s)</span>
  </div>
  <div class="panel-block">
    <strong>Director:</strong>
    <span class="value"><a href="#">某导演</a></span>
  </div>
  <div class="panel-block">
    <strong>Maker:</strong>
    <span class="value"><a href="#">S1 NO.1 STYLE</a></span>
  </div>
  <div class="panel-block">
    <strong>Label:</strong>
    <span class="value"><a href="#">S1</a></span>
  </div>
  <div class="panel-block">
    <strong>Series:</strong>
    <span class="value"><a href="#">某系列</a></span>
  </div>
  <div class="panel-block">
    <strong>Tags:</strong>
    <span class="value">
      <a href="#">美少女</a>
      <a href="#">高清</a>
    </span>
  </div>
  <div class="panel-block">
    <strong>Actor(s):</strong>
    <span class="value">
      <a href="#">天使萌</a>♀<a href="#">桃乃木かな</a>♀<a href="#">某男优</a>♂
    </span>
  </div>
  <div class="panel-block">
    <strong>Rating:</strong>
    <span class="value">4.52, by 123 users</span>
  </div>
</nav>
"""

_DETAIL_HTML_MINIMAL = """
<h2 class="title">
  <strong class="current-title">只有标题</strong>
</h2>
"""


# ------------------------------------------------------------------
# 测试：_find_detail_url
# ------------------------------------------------------------------

class TestFindDetailUrl:
    def setup_method(self):
        self.s = _make_scraper()

    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def test_finds_exact_match(self):
        url = self.s._find_detail_url(self._soup(_SEARCH_HTML_HIT), "SSIS-001")
        assert url == "https://javdb.com/v/BmVw7"

    def test_case_insensitive_match(self):
        url = self.s._find_detail_url(self._soup(_SEARCH_HTML_HIT), "ssis-001")
        assert url == "https://javdb.com/v/BmVw7"

    def test_returns_none_when_no_match(self):
        url = self.s._find_detail_url(self._soup(_SEARCH_HTML_NO_MATCH), "SSIS-001")
        assert url is None

    def test_returns_none_on_empty_page(self):
        url = self.s._find_detail_url(self._soup("<html></html>"), "SSIS-001")
        assert url is None


# ------------------------------------------------------------------
# 测试：_parse_detail
# ------------------------------------------------------------------

class TestParseDetail:
    def setup_method(self):
        self.s = _make_scraper()
        self.soup = BeautifulSoup(_DETAIL_HTML, "lxml")
        self.result = self.s._parse_detail(self.soup, "https://javdb.com/v/BmVw7")

    def test_title(self):
        assert self.result["title"] == "某某标题"

    def test_original_title(self):
        assert self.result["original_title"] == "某某タイトル"

    def test_poster_url(self):
        assert self.result["poster_url"] == "https://pics.example.com/cover.jpg"

    def test_fanart_url(self):
        assert self.result["fanart_url"] == "https://pics.example.com/cover.jpg"

    def test_av_code(self):
        # ID 分两个 <a> 元素：SSIS + -001，拼接后大写
        assert self.result["av_code"] == "SSIS-001"

    def test_release_date_and_year(self):
        assert self.result["release_date"] == "2021-01-15"
        assert self.result["year"] == 2021

    def test_duration(self):
        assert self.result["duration"] == 120

    def test_director(self):
        assert self.result["director"] == "某导演"

    def test_studio(self):
        assert self.result["studio"] == "S1 NO.1 STYLE"

    def test_label(self):
        assert self.result["label"] == "S1"

    def test_series(self):
        assert self.result["series"] == "某系列"

    def test_genres(self):
        assert self.result["genres"] == ["美少女", "高清"]

    def test_actresses_filters_female_only(self):
        # 三位演员：天使萌♀、桃乃木かな♀、某男优♂ → 只保留♀
        assert self.result["actresses"] == ["天使萌", "桃乃木かな"]

    def test_rating(self):
        assert self.result["rating"] == pytest.approx(4.52)

    def test_source(self):
        assert self.result["source"] == "javdb"

    def test_minimal_html_does_not_crash(self):
        soup = BeautifulSoup(_DETAIL_HTML_MINIMAL, "lxml")
        result = self.s._parse_detail(soup, "https://javdb.com/v/xxx")
        assert result["title"] == "只有标题"
        assert "rating" not in result
        assert "actresses" not in result


# ------------------------------------------------------------------
# 测试：_extract_female_actors
# ------------------------------------------------------------------

class TestExtractFemaleActors:
    def setup_method(self):
        self.s = _make_scraper()

    def _value_el(self, html: str):
        return BeautifulSoup(html, "lxml").select_one("span")

    def test_filters_female_only(self):
        html = '<span><a>A</a>♀<a>B</a>♂<a>C</a>♀</span>'
        result = JavDBScraper._extract_female_actors(self._value_el(html))
        assert result == ["A", "C"]

    def test_no_gender_marker_returns_all(self):
        """无性别标记时返回全部演员（兼容旧格式）。"""
        html = '<span><a>天使萌</a><a>桃乃木かな</a></span>'
        result = JavDBScraper._extract_female_actors(self._value_el(html))
        assert result == ["天使萌", "桃乃木かな"]

    def test_all_male_returns_empty(self):
        html = '<span><a>某男优</a>♂<a>另一男优</a>♂</span>'
        result = JavDBScraper._extract_female_actors(self._value_el(html))
        assert result == []

    def test_empty_returns_empty(self):
        html = '<span></span>'
        result = JavDBScraper._extract_female_actors(self._value_el(html))
        assert result == []


# ------------------------------------------------------------------
# 测试：search()（端到端，mock HTTP）
# ------------------------------------------------------------------

class TestSearch:
    @patch("scrapers.base.time.sleep")
    def test_search_returns_detail_on_hit(self, mock_sleep):
        s = _make_scraper()
        s._client.get = MagicMock(side_effect=[
            _mock_resp(_SEARCH_HTML_HIT),   # 搜索页
            _mock_resp(_DETAIL_HTML),        # 详情页
        ])

        result = s.search("SSIS-001")

        assert result is not None
        assert result["title"] == "某某标题"
        assert result["actresses"] == ["天使萌", "桃乃木かな"]

    @patch("scrapers.base.time.sleep")
    def test_search_returns_none_when_no_match(self, mock_sleep):
        s = _make_scraper()
        s._client.get = MagicMock(return_value=_mock_resp(_SEARCH_HTML_NO_MATCH))

        result = s.search("SSIS-001")

        assert result is None
        # 无匹配时不请求详情页
        assert s._client.get.call_count == 1

    @patch("scrapers.base.time.sleep")
    def test_search_returns_none_on_404(self, mock_sleep):
        s = _make_scraper()
        s._client.get = MagicMock(return_value=_mock_resp("", status=404))

        result = s.search("SSIS-001")

        assert result is None

    @patch("scrapers.base.time.sleep")
    def test_get_detail_returns_none_on_404(self, mock_sleep):
        s = _make_scraper()
        s._client.get = MagicMock(return_value=_mock_resp("", status=404))

        result = s.get_detail("https://javdb.com/v/NotExist")

        assert result is None


# ------------------------------------------------------------------
# 测试：封面 URL 协议补全
# ------------------------------------------------------------------

class TestPosterUrlProtocol:
    def setup_method(self):
        self.s = _make_scraper()

    def test_relative_protocol_prepended(self):
        html = '<img class="video-cover" src="//pics.example.com/cover.jpg" />'
        soup = BeautifulSoup(html, "lxml")
        result = self.s._parse_detail(soup, "https://javdb.com/v/x")
        assert result["poster_url"].startswith("https:")
        assert result["fanart_url"].startswith("https:")

    def test_absolute_url_unchanged(self):
        html = '<img class="video-cover" src="https://pics.example.com/cover.jpg" />'
        soup = BeautifulSoup(html, "lxml")
        result = self.s._parse_detail(soup, "https://javdb.com/v/x")
        assert result["poster_url"] == "https://pics.example.com/cover.jpg"
        assert result["fanart_url"] == "https://pics.example.com/cover.jpg"
