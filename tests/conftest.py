"""
测试环境初始化：将 MediaMatrix 根目录加入 sys.path，
使 providers.base、core.plugin_engine 等宿主模块可被 import。

优先使用 MEDIAMATRIX_ROOT 环境变量；
未设置时自动尝试相对路径（适用于开发时两仓库并列存放的情况）。
"""
import os
import sys
from pathlib import Path


def _find_host_root() -> Path | None:
    if env := os.environ.get("MEDIAMATRIX_ROOT"):
        p = Path(env)
        return p if p.exists() else None
    # 两仓库并列时：../MediaMatrix
    candidate = Path(__file__).parent.parent.parent / "MediaMatrix"
    return candidate if candidate.exists() else None


_host_root = _find_host_root()
if _host_root:
    sys.path.insert(0, str(_host_root))
else:
    import warnings
    warnings.warn(
        "未找到 MediaMatrix 根目录。依赖宿主模块的测试将失败。\n"
        "请设置 MEDIAMATRIX_ROOT 环境变量，或使用:\n"
        "  PYTHONPATH=/path/to/MediaMatrix pytest tests/",
        RuntimeWarning,
        stacklevel=1,
    )
