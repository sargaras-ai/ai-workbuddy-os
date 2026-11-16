#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""二级业务测试最小骨架（示例，可直接抄去改成你的）。

它演示四件事，正是闸门要的四件事：

1. 摘要行必须形如   PASS 3 / FAIL 0
   闸门只看这一行：PASS 的数必须 ≥ 1，且 FAIL 必须为 0。
   写一行 sys.exit(0) 骗不过它——没有摘要行就判红。
2. 有断言失败 → 打印 FAIL 明细 + 摘要里 FAIL 数 > 0 + 退出码 1。
3. 一条断言都没有 = 0 条测试，同样判红（空测试＝仪式）。
4. 用例名带 aN_ 前缀，与项目卡第 9 段的「测试标识」列一一对应：
   卡里写 `→ a1_due_when_20_days`，这里就有 `a1_due_when_20_days`，名字逐字一致。
   card_gate.py 的 G7 查的就是这件事——卡里有几条验收，就得有几个不同的名字，
   且每个名字都能在本文件的源码里找到。

本仓库不含示例的业务代码，所以下面几个函数是**被测逻辑的最小替身**。
真实项目请 `from app import due_days, ...`——只要名字在「卡 / 本文件 / 被测模块」
三处对得上，闸门就认。
"""

import sys
from datetime import date

PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        print("FAIL  %s | 期望 %r 实际 %r" % (name, want, got))


# ---- 被测逻辑的最小替身（真实项目换成 import 你的模块）----
def parse_date(s):
    """非法日期返回 None，绝不猜一个凑合的日期顶上。"""
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def due_days(last, today):
    """距上次浇水过了几天；日期非法返回 None（不返回 0——0 会被当成「刚浇过」而漏浇）。"""
    a, b = parse_date(last), parse_date(today)
    if a is None or b is None:
        return None
    return (b - a).days


def should_water(last, today, interval=7):
    d = due_days(last, today)
    return d is not None and d >= interval


def mark_watered(rec, today):
    """标记「今天浇完了」：只写回 last_water，其余字段不动。"""
    rec = dict(rec)
    rec["last_water"] = today
    return rec


# ---- 三条用例，对应卡第 9 段的 1 / 2 / 3 ----
# 手算的期望值（不是让程序算完自己跟自己比）：
#   2026-01-01 → 2026-01-21 = 20 天，且 20 ≥ 默认间隔 7 → (20, True)
#   "2026-13-45" 是非法日期 → None
#   标记已浇后 last_water 必须正好等于今天 → "2026-01-21"
check("a1_due_when_20_days",
      (due_days("2026-01-01", "2026-01-21"), should_water("2026-01-01", "2026-01-21")),
      (20, True))
check("a2_reject_illegal_date", parse_date("2026-13-45"), None)
check("a3_mark_watered_today",
      mark_watered({"last_water": "2026-01-01"}, "2026-01-21")["last_water"],
      "2026-01-21")

print("PASS %d / FAIL %d" % (PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
