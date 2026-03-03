"""
tests/test_provider.py — JavExpertProvider 单元测试

依赖宿主 providers.base，需 MEDIAMATRIX_ROOT 在 sys.path 中（conftest.py 处理）。
所有 HTTP 请求通过 mock scraper 替代。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest.py 已将 MediaMatrix 加入 sys.path
# 同时将插件根目录加入，确保 provider 模块可被 import
sys.path.insert(0, str(Path(__file__).parent.parent))

from providers.base import MediaDetail, MediaQuery, SearchResult
from jav_expert.provider import JavExpertProvider


# ------------------------------------------------------------------
# 工具
# ------------------------------------------------------------------

def _make_provider(dmm_enabled: bool = False) -> JavExpertProvider:
    return JavExpertProvider({
        "sources": {
            "javdb": {
                "base_url": "https://javdb.com",
                "delay": 0.0,
                "max_retries": 1,
                "user_agents": ["TestAgent/1.0"],
            },
            "dmm": {
                "enabled": dmm_enabled,
                "base_url": "https://www.dmm.co.jp",
                "delay": 0.0,
                "max_retries": 1,
                "user_agents": ["TestAgent/1.0"],
                "cid_strategy": "pattern_then_search",
            },
        }
    })


def _javdb_data(**overrides) -> dict:
    base = {
        "title": "JavDB标题",
        "original_title": "JavDB原タイトル",
        "year": 2021,
        "release_date": "2021-01-15",
        "poster_url": "https://javdb.com/cover.jpg",
        "fanart_url": None,
        "rating": 4.5,
        "genres": ["美少女", "高清"],
        "actresses": ["天使萌"],
        "director": "JavDB导演",
        "studio": "JavDB片商",
        "label": "JavDB发行商",
        "series": "JavDB系列",
        "duration": 120,
        "source": "javdb",
    }
    base.update(overrides)
    return base


def _dmm_data(**overrides) -> dict:
    base = {
        "title": "DMM公式タイトル",
        "original_title": "DMM公式タイトル",
        "year": 2021,
        "release_date": "2021-01-15",
        "poster_url": "https://pics.dmm.co.jp/ssis00001pl.jpg",
        "fanart_url": "https://pics.dmm.co.jp/ssis00001pl.jpg",
        "director": "DMM監督",
        "studio": "DMMメーカー",
        "label": "DMM레이블",
        "series": "DMMシリーズ",
        "duration": 125,
        "actresses": ["天使もえ"],
        "source": "dmm",
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------
# 测试：番号提取
# ------------------------------------------------------------------

class TestExtractAvCode:
    def test_standard_format(self):
        assert JavExpertProvider._extract_av_code("SSIS-001.mkv") == "SSIS-001"

    def test_uppercase_normalize(self):
        assert JavExpertProvider._extract_av_code("ssis-001") == "SSIS-001"

    def test_long_prefix(self):
        assert JavExpertProvider._extract_av_code("CAWD-001") == "CAWD-001"

    def test_stars_format(self):
        assert JavExpertProvider._extract_av_code("STARS-500") == "STARS-500"

    def test_fc2_format(self):
        assert JavExpertProvider._extract_av_code("FC2-PPV-1234567") == "FC2-PPV-1234567"

    def test_fc2_takes_priority_over_standard(self):
        # FC2 正则优先
        code = JavExpertProvider._extract_av_code("FC2-PPV-1234567.mkv")
        assert code == "FC2-PPV-1234567"

    def test_normal_movie_returns_none(self):
        assert JavExpertProvider._extract_av_code("Inception 2010") is None

    def test_chinese_movie_returns_none(self):
        assert JavExpertProvider._extract_av_code("流浪地球2 2023") is None

    def test_empty_string_returns_none(self):
        assert JavExpertProvider._extract_av_code("") is None

    def test_path_with_av_code(self):
        assert JavExpertProvider._extract_av_code("/media/av/SSIS-001.mp4") == "SSIS-001"


# ------------------------------------------------------------------
# 测试：search()
# ------------------------------------------------------------------

class TestSearch:
    def test_returns_search_result_for_av_code(self):
        p = _make_provider()
        query = MediaQuery(title="SSIS-001.mkv", media_type="movie")
        results = p.search(query)

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, SearchResult)
        assert r.provider_id == "movie:SSIS-001"
        assert r.media_type == "movie"
        assert r.provider == "jav_expert"

    def test_returns_empty_for_normal_movie(self):
        p = _make_provider()
        query = MediaQuery(title="Inception 2010", media_type="movie")
        assert p.search(query) == []

    def test_returns_empty_for_tv_content(self):
        p = _make_provider()
        query = MediaQuery(title="Breaking Bad S01E01", media_type="tv")
        assert p.search(query) == []

    def test_year_passed_through(self):
        p = _make_provider()
        query = MediaQuery(title="SSIS-001", media_type="movie", year=2021)
        results = p.search(query)
        assert results[0].year == 2021


# ------------------------------------------------------------------
# 测试：get_detail() — 仅 JavDB
# ------------------------------------------------------------------

class TestGetDetailJavdbOnly:
    def setup_method(self):
        self.p = _make_provider(dmm_enabled=False)
        self.p._javdb.search = MagicMock(return_value=_javdb_data())

    def test_returns_media_detail(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert isinstance(result, MediaDetail)

    def test_provider_id(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.provider_id == "movie:SSIS-001"

    def test_title(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.title == "JavDB标题"

    def test_rating(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.rating == pytest.approx(4.5)

    def test_genres(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.genres == ["美少女", "高清"]

    def test_extra_av_code(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.extra["av_code"] == "SSIS-001"

    def test_extra_actresses(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.extra["actresses"] == ["天使萌"]

    def test_extra_source_is_javdb(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.extra["source"] == "javdb"

    def test_returns_none_when_javdb_has_no_result(self):
        self.p._javdb.search = MagicMock(return_value=None)
        result = self.p.get_detail("movie:SSIS-001")
        assert result is None

    def test_dmm_not_called_when_disabled(self):
        self.p.get_detail("movie:SSIS-001")
        assert self.p._dmm is None


# ------------------------------------------------------------------
# 测试：get_detail() — DMM 开启时字段合并
# ------------------------------------------------------------------

class TestGetDetailWithDmm:
    def setup_method(self):
        self.p = _make_provider(dmm_enabled=True)
        self.p._javdb.search = MagicMock(return_value=_javdb_data())
        self.p._dmm.search = MagicMock(return_value=_dmm_data())

    def test_title_from_dmm(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.title == "DMM公式タイトル"

    def test_poster_from_dmm(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert "dmm" in result.poster_url

    def test_director_from_dmm(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.extra["director"] == "DMM監督"

    def test_rating_kept_from_javdb(self):
        """DMM 无评分，rating 始终来自 JavDB。"""
        result = self.p.get_detail("movie:SSIS-001")
        assert result.rating == pytest.approx(4.5)

    def test_genres_kept_from_javdb(self):
        """genres 始终保留 JavDB（DMM 无 genres 时也如此）。"""
        result = self.p.get_detail("movie:SSIS-001")
        assert result.genres == ["美少女", "高清"]

    def test_actresses_from_dmm(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.extra["actresses"] == ["天使もえ"]

    def test_source_is_javdb_plus_dmm(self):
        result = self.p.get_detail("movie:SSIS-001")
        assert result.extra["source"] == "javdb+dmm"

    def test_falls_back_to_javdb_when_dmm_returns_none(self):
        self.p._dmm.search = MagicMock(return_value=None)
        result = self.p.get_detail("movie:SSIS-001")
        assert result.title == "JavDB标题"
        assert result.extra["source"] == "javdb"


# ------------------------------------------------------------------
# 测试：_merge() 字段优先级
# ------------------------------------------------------------------

class TestMerge:
    def test_dmm_overrides_title(self):
        merged = JavExpertProvider._merge(
            _javdb_data(title="JavDB"),
            _dmm_data(title="DMM"),
        )
        assert merged["title"] == "DMM"

    def test_dmm_overrides_poster_url(self):
        merged = JavExpertProvider._merge(
            _javdb_data(poster_url="http://javdb/cover.jpg"),
            _dmm_data(poster_url="http://dmm/cover.jpg"),
        )
        assert merged["poster_url"] == "http://dmm/cover.jpg"

    def test_javdb_rating_not_overridden(self):
        """rating 字段不在 DMM 优先列表，始终保留 JavDB 值。"""
        merged = JavExpertProvider._merge(
            _javdb_data(rating=4.5),
            _dmm_data(),  # dmm_data 无 rating 字段
        )
        assert merged["rating"] == pytest.approx(4.5)

    def test_javdb_genres_not_overridden(self):
        merged = JavExpertProvider._merge(
            _javdb_data(genres=["美少女", "高清"]),
            _dmm_data(),
        )
        assert merged["genres"] == ["美少女", "高清"]

    def test_dmm_empty_field_does_not_override(self):
        """DMM 字段为空时，保留 JavDB 值。"""
        merged = JavExpertProvider._merge(
            _javdb_data(director="JavDB导演"),
            _dmm_data(director=""),
        )
        assert merged["director"] == "JavDB导演"

    def test_dmm_actresses_override_javdb(self):
        merged = JavExpertProvider._merge(
            _javdb_data(actresses=["天使萌"]),
            _dmm_data(actresses=["天使もえ", "桃乃木かな"]),
        )
        assert merged["actresses"] == ["天使もえ", "桃乃木かな"]

    def test_source_marked_as_combined(self):
        merged = JavExpertProvider._merge(_javdb_data(), _dmm_data())
        assert merged["source"] == "javdb+dmm"


# ------------------------------------------------------------------
# 测试：_to_media_detail() 结构完整性
# ------------------------------------------------------------------

class TestToMediaDetail:
    def test_all_required_fields_present(self):
        detail = JavExpertProvider._to_media_detail(
            _javdb_data(), "SSIS-001", "movie:SSIS-001"
        )
        assert detail.provider_id == "movie:SSIS-001"
        assert detail.media_type == "movie"
        assert detail.provider == "jav_expert"
        assert detail.logo_url is None

    def test_title_fallback_to_av_code(self):
        """title 为空时使用番号作为标题。"""
        data = _javdb_data(title="")
        detail = JavExpertProvider._to_media_detail(data, "SSIS-001", "movie:SSIS-001")
        assert detail.title == "SSIS-001"

    def test_original_title_fallback_to_title(self):
        data = _javdb_data(original_title=None)
        detail = JavExpertProvider._to_media_detail(data, "SSIS-001", "movie:SSIS-001")
        assert detail.original_title == data["title"]

    def test_extra_keys(self):
        detail = JavExpertProvider._to_media_detail(
            _javdb_data(), "SSIS-001", "movie:SSIS-001"
        )
        for key in ("av_code", "actresses", "director", "studio", "label", "series", "duration", "source"):
            assert key in detail.extra
