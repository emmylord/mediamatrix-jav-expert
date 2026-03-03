"""
tests/test_plugin.py — JavExpertPlugin 单元测试

不依赖真实网络，通过 mock 验证插件初始化逻辑。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# 在 import jav_expert 之前 mock 宿主模块，避免找不到 core.plugin_engine
import types

_fake_core = types.ModuleType("core")
_fake_engine = types.ModuleType("core.plugin_engine")

class _FakeBasePlugin:
    name: str = ""
    version: str = "0.0.1"
    def on_init(self, config, **kwargs): pass
    def after_scraped(self, media_item): pass
    def on_error(self, error, media_item): pass

_fake_engine.BasePlugin = _FakeBasePlugin
sys.modules.setdefault("core", _fake_core)
sys.modules.setdefault("core.plugin_engine", _fake_engine)

# mock providers.base 供 provider.py 使用
_fake_providers = types.ModuleType("providers")
_fake_base = types.ModuleType("providers.base")

from dataclasses import dataclass, field
from typing import Optional as Opt

@dataclass
class _FakeMediaQuery:
    title: str
    media_type: str
    year: Opt[int] = None
    extra: dict = field(default_factory=dict)

@dataclass
class _FakeSearchResult:
    provider_id: str
    title: str
    year: Opt[int]
    media_type: str
    provider: str

@dataclass
class _FakeMediaDetail:
    provider_id: str
    title: str
    original_title: str
    year: Opt[int]
    media_type: str
    overview: str
    genres: list
    poster_url: Opt[str]
    fanart_url: Opt[str]
    logo_url: Opt[str]
    rating: Opt[float]
    provider: str
    extra: dict = field(default_factory=dict)

class _FakeBaseProvider:
    name: str = ""
    media_types: list = []
    priority: int = 10

_fake_base.BaseProvider = _FakeBaseProvider
_fake_base.MediaQuery = _FakeMediaQuery
_fake_base.MediaDetail = _FakeMediaDetail
_fake_base.SearchResult = _FakeSearchResult
sys.modules.setdefault("providers", _fake_providers)
sys.modules.setdefault("providers.base", _fake_base)

from jav_expert.jav_expert import JavExpertPlugin, _deep_merge


# ------------------------------------------------------------------
# 工具
# ------------------------------------------------------------------

def _make_plugin() -> JavExpertPlugin:
    return JavExpertPlugin()


def _minimal_host_config() -> dict:
    return {}  # 无 jav_expert 节，完全使用默认值


# ------------------------------------------------------------------
# 测试：on_init — registry 缺失
# ------------------------------------------------------------------

class TestOnInitNoRegistry:
    def test_logs_warning_and_returns_when_no_registry(self, caplog):
        import logging
        plugin = _make_plugin()
        with caplog.at_level(logging.WARNING, logger="jav_expert"):
            plugin.on_init(config=_minimal_host_config())  # 未传 registry
        assert "ProviderRegistry" in caplog.text

    def test_does_not_raise_when_no_registry(self):
        plugin = _make_plugin()
        plugin.on_init(config=_minimal_host_config())  # 不应抛出


# ------------------------------------------------------------------
# 测试：on_init — 正常流程
# ------------------------------------------------------------------

class TestOnInitWithRegistry:
    def test_registers_provider(self):
        plugin = _make_plugin()
        mock_registry = MagicMock()
        plugin.on_init(config=_minimal_host_config(), registry=mock_registry)
        mock_registry.register.assert_called_once()

    def test_registered_provider_is_jav_expert(self):
        from jav_expert.provider import JavExpertProvider
        plugin = _make_plugin()
        mock_registry = MagicMock()
        plugin.on_init(config=_minimal_host_config(), registry=mock_registry)
        registered = mock_registry.register.call_args.args[0]
        assert isinstance(registered, JavExpertProvider)

    def test_dmm_disabled_by_default(self):
        plugin = _make_plugin()
        mock_registry = MagicMock()
        plugin.on_init(config=_minimal_host_config(), registry=mock_registry)
        provider = mock_registry.register.call_args.args[0]
        assert not provider._dmm_enabled

    def test_user_config_enables_dmm(self):
        plugin = _make_plugin()
        mock_registry = MagicMock()
        host_cfg = {"jav_expert": {"sources": {"dmm": {"enabled": True}}}}
        plugin.on_init(config=host_cfg, registry=mock_registry)
        provider = mock_registry.register.call_args.args[0]
        assert provider._dmm_enabled


# ------------------------------------------------------------------
# 测试：_load_config 合并逻辑
# ------------------------------------------------------------------

class TestLoadConfig:
    def test_loads_defaults(self):
        plugin = _make_plugin()
        cfg = plugin._load_config({})
        assert "sources" in cfg
        assert cfg["sources"]["javdb"]["enabled"] is True
        assert cfg["sources"]["dmm"]["enabled"] is False

    def test_user_override_merged(self):
        plugin = _make_plugin()
        cfg = plugin._load_config({
            "jav_expert": {
                "sources": {
                    "javdb": {"delay": 5.0},
                    "dmm": {"enabled": True},
                }
            }
        })
        assert cfg["sources"]["javdb"]["delay"] == 5.0
        assert cfg["sources"]["dmm"]["enabled"] is True
        # 未覆盖的字段保留默认值
        assert cfg["sources"]["javdb"]["base_url"] == "https://javdb.com"


# ------------------------------------------------------------------
# 测试：_deep_merge
# ------------------------------------------------------------------

class TestDeepMerge:
    def test_flat_override(self):
        base = {"a": 1, "b": 2}
        _deep_merge(base, {"b": 99, "c": 3})
        assert base == {"a": 1, "b": 99, "c": 3}

    def test_nested_merge(self):
        base = {"x": {"a": 1, "b": 2}}
        _deep_merge(base, {"x": {"b": 99, "c": 3}})
        assert base == {"x": {"a": 1, "b": 99, "c": 3}}

    def test_non_dict_value_replaced(self):
        base = {"x": {"nested": True}}
        _deep_merge(base, {"x": "now_a_string"})
        assert base["x"] == "now_a_string"

    def test_empty_override_no_change(self):
        base = {"a": 1}
        _deep_merge(base, {})
        assert base == {"a": 1}
