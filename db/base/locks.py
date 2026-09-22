"""进程内资源锁。

SQLite 没有行级锁，"检查空闲 -> 落库"之间存在竞态：两个请求可能同时判断
同一技师/工位空闲，然后都写入工单。这里用一个进程级锁把"检查+写入"串起来，
保证单体部署下不会排出冲突工单。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

# 排班写入串行化锁（可重入，避免嵌套调用死锁）
resource_lock = threading.RLock()


@contextmanager
def booking_critical_section():
    """进入排班写入临界区。"""

    resource_lock.acquire()
    try:
        yield
    finally:
        resource_lock.release()