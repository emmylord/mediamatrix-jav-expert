"""
conftest.py（插件根目录）— pytest 全局初始化

将当前目录注册为 "jav_expert" 包，供所有测试文件使用。

没有这个注册，Python 会在 sys.path 里找到 jav_expert.py 并把它当作
顶层模块（而非包入口），导致相对 import（from .provider import ...）失败。
有了这个注册，jav_expert.py 以 "jav_expert.jav_expert" 子模块的身份加载，
相对 import 的 __package__ = "jav_expert" 才正确。
"""

import sys
import types
from pathlib import Path

_plugin_root = Path(__file__).parent

if "jav_expert" not in sys.modules:
    _pkg = types.ModuleType("jav_expert")
    _pkg.__path__ = [str(_plugin_root)]
    _pkg.__package__ = "jav_expert"
    sys.modules["jav_expert"] = _pkg
