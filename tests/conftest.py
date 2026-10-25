"""pytest 配置：把插件目录加入导入路径，测试可直接 import 纯函数模块。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
