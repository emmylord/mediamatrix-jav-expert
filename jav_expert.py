"""
jav_expert.py — JavExpertPlugin 插件入口

加载流程：
  1. PluginEngine 扫描 plugins/jav_expert/ 目录，发现此文件
  2. 触发 on_init(config, registry=registry)
  3. 合并 config_default.yaml 与用户 settings.yaml 中的 jav_expert: 节
  4. 构造 JavExpertProvider 并注册到 ProviderRegistry
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

from core.plugin_engine import BasePlugin

from .provider import JavExpertProvider

logger = logging.getLogger(__name__)


class JavExpertPlugin(BasePlugin):
    name = "jav_expert"
    version = "0.1.0"

    def on_init(self, config: dict, **kwargs) -> None:
        registry = kwargs.get("registry")
        if registry is None:
            logger.warning(
                "[JavExpert] 未获取到 ProviderRegistry，刮削功能不可用。"
                "请确认宿主版本已支持 registry 注入（main.py trigger 传入 registry=registry）。"
            )
            return

        plugin_cfg = self._load_config(config)
        self._provider = JavExpertProvider(plugin_cfg)
        registry.register(self._provider)

        sources = plugin_cfg.get("sources", {})
        dmm_on = sources.get("dmm", {}).get("enabled", False)
        logger.info(
            "[JavExpert] 插件初始化完成 | JavDB=启用 | DMM=%s",
            "启用" if dmm_on else "禁用",
        )

    # ------------------------------------------------------------------
    # 配置加载
    # ------------------------------------------------------------------

    def _load_config(self, host_config: dict) -> dict:
        """
        加载插件配置：
          1. 读取插件目录内的 config_default.yaml（默认值）
          2. 深度合并用户在主项目 settings.yaml 中的 jav_expert: 节
        """
        default_path = Path(__file__).parent / "config_default.yaml"
        with open(default_path, encoding="utf-8") as f:
            cfg: dict = yaml.safe_load(f)

        user_cfg = host_config.get("jav_expert", {})
        if user_cfg:
            _deep_merge(cfg, user_cfg)

        return cfg


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> None:
    """将 override 深度合并到 base（原地修改 base）。"""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
