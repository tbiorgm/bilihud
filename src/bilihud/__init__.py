"""Top-level package for bilihud."""

import sys
import os

# 优先查找包内的 vendor (安装模式)
_local_vendor = os.path.join(os.path.dirname(__file__), 'vendor')
# 其次查找项目根目录的 vendor (开发模式)
# 开发模式结构: src/bilihud/__init__.py -> ../../vendor/blivedm
_dev_vendor = os.path.join(os.path.dirname(__file__), '..', '..', 'vendor', 'blivedm')

if os.path.exists(os.path.join(_local_vendor, 'blivedm')):
    if _local_vendor not in sys.path:
        sys.path.insert(0, _local_vendor)
elif os.path.exists(_dev_vendor):
    if _dev_vendor not in sys.path:
        sys.path.insert(0, _dev_vendor)

