#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""二级业务测试最小骨架（示例，可直接抄去改成你的）。

它演示三件事，也正是闸门要的三件事：

1. 摘要行必须形如   PASS 3 / FAIL 0
   闸门只看这一行：PASS 的数必须 ≥ 1，且 FAIL 必须为 0。
   写一行 sys.exit(0) 骗不过它——没有摘要行就判红。
2. 有断言失败 → 打印 FAIL 明细 + 摘要里 FAIL 数 > 0 + 退出码 1。
3. 一条断言都没有 = 0 条测试，同样判红（空测试＝仪式）。

改法：把 settle() 换成你的业务函数（结算、赔率、计费、权限…），
把手算出来的期望值钉进 check()。宁可手算三组，也别让它自己算完自己比——
那样的测试永远绿，等于没有。
"""

import sys

PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        print("FAIL  %s | 期望 %r 实际 %r" % (name, want, got))


def settle(stake, odds, won):
    """示例业务函数：命中则按赔率返还，未命中则亏掉本金。"""
    return stake * odds if won else -stake


# 手算的期望值（不是让程序算完自己比）：
#   100 本金 × 1.5 命中   → 150
#   100 本金 × 1.5 未命中 → -100
#   100 本金 × 2.0 命中   → 200
check("命中 100×1.5", settle(100, 1.5, True), 150.0)
check("未中 100", settle(100, 1.5, False), -100)
check("打平 100×2.0", settle(100, 2.0, True), 200.0)

print("PASS %d / FAIL %d" % (PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
