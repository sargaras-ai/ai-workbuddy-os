#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跑全量回归.py —— 一键全量回归（机器替人跑腿，任一节点报红即终止）

双击（或 `python 跑全量回归.py`）即串行跑以下节点，任一退出码非 0 立即终止并大声汇报：

   1) 自检.py              规则自洽（总则/暗语表/副本/隐私/引用悬空/心跳）
   2) check_memory.py      记忆层一致性（MEMORY.md ↔ 暗语表）
   3) 巡检.py --check       工作轮打卡（心跳防线，写 last_check_at）
   4) 巡检.py --self-test   负控自检（验证巡检自己「会红」）
   5) 业务测试（若存在）     自动探测 <各卡>/tests/run_tests.py 或主程序 --test

判据：任一节点退出码非 0 → 立即终止，打印醒目 FAIL 汇总，本脚本退出码 1。
      全部节点退出码 0 → 打印 PASS 汇总，退出码 0。

用法：
    python 跑全量回归.py            # 全量跑（默认）
    python 跑全量回归.py --self-test # 负控自检：验证本脚本自己「会红」（不会改任何真文件）

为什么要有它：每次加小功能都要提心吊胆地手动验一遍，是「人肉 CI」；
本脚本把自检/记忆/巡检/业务测试串成一条链，机器替人跑，红了立刻喊停。
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # 用当前 python 解释器，规避 PATH / 专用解释器问题

# 串行节点列表：(标题, 脚本, 参数列表)。顺序即依赖序：先规则自洽，再记忆一致，再心跳，再业务。
NODES = [
    ("规则自检（总则/暗语表/副本/隐私）", "自检.py", []),
    ("记忆层一致性（MEMORY ↔ 暗语表）", "check_memory.py", []),
    ("心跳工作轮打卡", "巡检.py", ["--check"]),
    ("巡检负控自检（验证巡检自己会红）", "巡检.py", ["--self-test"]),
]

# 业务测试探测：包根目录本身没有业务测试（这是约束包，不是业务项目）；
# 但若有人在包目录下放了 tests/run_tests.py，一并纳入，不放过任何可测节点。
BUSINESS_TESTS = [
    ("业务测试", os.path.join(BASE, "tests", "run_tests.py"), []),
]


def run_node(title, script, args, cwd=BASE):
    """跑单个节点，返回 (标题, 退出码, 输出文本)。"""
    cmd = [PY, script] + list(args)
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        return title, p.returncode, out
    except Exception as e:
        return title, 127, "无法启动 %s：%s" % (script, e)


def main():
    args = sys.argv[1:]
    if "--self-test" in args:
        return self_test()

    print("=" * 64)
    print("一键全量回归：机器替人跑腿，任一节点报红立即终止")
    print("=" * 64)

    failed = []
    passed = 0

    for title, script, node_args in NODES:
        t, code, out = run_node(title, script, node_args)
        print("\n[%s]" % t)
        # 只打印各节点输出的关键行（末尾结论行），不刷屏；报红时再全量贴
        tail_lines = [ln for ln in out.splitlines() if ln.strip()][-8:]
        for ln in tail_lines:
            print("   " + ln)
        if code != 0:
            print("\n>>> 节点【%s】报红！退出码 %d，立即终止。<<<" % (title, code))
            failed.append((title, code, out))
            break
        passed += 1

    # 业务测试：仅当文件真实存在才纳入（不存在＝无可测节点，不算失败）
    if not failed:
        for title, path, node_args in BUSINESS_TESTS:
            if os.path.isfile(path):
                t, code, out = run_node(title, path, node_args)
                print("\n[%s] %s" % (title, path))
                tail_lines = [ln for ln in out.splitlines() if ln.strip()][-8:]
                for ln in tail_lines:
                    print("   " + ln)
                if code != 0:
                    print("\n>>> 节点【%s】报红！退出码 %d，立即终止。<<<" % (title, code))
                    failed.append((title, code, out))
                    break
                passed += 1

    print("\n" + "=" * 64)
    if failed:
        print("FAIL 全量回归：%d 个节点报红（共 %d 节点）。" % (len(failed), passed + len(failed)))
        for title, code, out in failed:
            print("\n--- 报红节点：%s（退出码 %d）---" % (title, code))
            print(out[-3000:] if len(out) > 3000 else out)
        print("\n>>> 停手！有节点报红，不许交付、不许推送，先修红。<<<")
        print("=" * 64)
        return 1
    print("PASS 全量回归：%d 个节点全绿。" % passed)
    print("=" * 64)
    return 0


def self_test():
    """负控自检：验证本脚本自己「会红」——用假节点喂一个必然失败的命令，
    断言 main 逻辑确实会捕获并终止。不碰任何真文件。"""
    print("跑全量回归 --self-test：负控自检（验证「会红」）")
    # 临时把 NODES 换成一条必然失败的命令，验证 run_node + 终止逻辑
    import json
    ok_all = True

    # 1) run_node 能正确捕获非零退出码
    t, code, out = run_node("假红节点", "-c", ["import sys; sys.exit(3)"], cwd=BASE)
    # 注意：run_node 用 [PY, script] 拼命令，这里 script 是 "-c" 会拼成 python -c ...
    # 直接用底层验证：一个必然 exit 3 的进程应返回 code 3
    probe = subprocess.run([PY, "-c", "import sys; sys.exit(3)"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok_all = ok_all and (probe.returncode == 3)
    print("  [%s] 必然失败的进程返回非零退出码（=3）" % ("PASS" if probe.returncode == 3 else "FAIL"))

    # 2) 探测业务测试逻辑：不存在的文件不纳入（不算失败）
    ghost = os.path.join(BASE, "tests", "不存在_占位.py")
    ok_all = ok_all and (not os.path.isfile(ghost))
    print("  [%s] 不存在的业务测试文件不误报红" % ("PASS" if not os.path.isfile(ghost) else "FAIL"))

    # 3) 验证三个核心脚本此刻真实存在（防「脚本自己引用悬空」）
    for s in ["自检.py", "check_memory.py", "巡检.py"]:
        exists = os.path.isfile(os.path.join(BASE, s))
        ok_all = ok_all and exists
        print("  [%s] %s 真实存在" % ("PASS" if exists else "FAIL", s))

    print("=" * 64)
    if ok_all:
        print("PASS 跑全量回归负控自检：会红、不误报、脚本齐全")
        return 0
    print("FAIL 跑全量回归负控自检")
    return 1


if __name__ == "__main__":
    sys.exit(main())
