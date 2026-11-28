# -*- coding: utf-8 -*-
"""提示词常量统一入口：聚合 common / legacy / lobster 三个子模块。

上游仓库缺少本文件，导致 ``from prompts import ...`` 抛出 ImportError，
这里显式重导出各子模块的公开名称。
"""
from .common import *  # noqa: F401,F403
from .legacy import *  # noqa: F401,F403
from .lobster import *  # noqa: F401,F403
