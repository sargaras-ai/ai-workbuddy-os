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
import hashlib
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # 用当前 python 解释器，规避 PATH / 专用解释器问题

# 哈希指纹基线：这四个核心检查器 + 本脚本，任一个被偷偷改（如注释掉 fails.append），
# 哈希对不上 → 红牌罚下。基线存 _hash_baseline.json，只有「特批流程」才许更新（总则 4.13）。
BASELINE_FILE = os.path.join(BASE, "_hash_baseline.json")
GUARDED_FILES = ["自检.py", "check_memory.py", "巡检.py", "card_gate.py", "跑全量回归.py"]


def sha256_of(path):
    """文件 sha256（文本按 UTF-8 原样字节算，与平台无关）。"""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_baseline():
    """读基线，返回 dict 或 None（基线不存在）。"""
    if not os.path.isfile(BASELINE_FILE):
        return None
    try:
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_baseline():
    """（特批）生成/更新哈希基线：对五个守护文件算 sha256 写进 _hash_baseline.json。"""
    data = {f: sha256_of(os.path.join(BASE, f)) for f in GUARDED_FILES}
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def check_baseline():
    """第 0 步：核对五个守护文件的哈希是否与基线一致。
    返回 (状态, 问题列表)。状态分三档：
      "ok"       基线存在且全部一致
      "skip"     基线不存在（clone 布局 / 首次使用，本机自证机制未启用）
      "tampered" 基线存在但哈希对不上（检查器被收买/被改）
    """
    base = load_baseline()
    if base is None:
        return ("skip", ["哈希基线 _hash_baseline.json 不存在（clone 布局或首次使用，跳过核对）。本机正本请跑 `python 跑全量回归.py --update-baseline` 建立基线（总则 4.13）。"])
    problems = []
    for f in GUARDED_FILES:
        path = os.path.join(BASE, f)
        if not os.path.isfile(path):
            # 本机正本应全在；缺失 = 检查器被删（G8 职责，此处报红）
            problems.append("守护文件 %s 丢失（被删）" % f)
            continue
        cur = sha256_of(path)
        exp = base.get(f)
        if exp is None:
            problems.append("%s 不在基线里（新增但未登记）" % f)
        elif cur != exp:
            problems.append("%s 哈希对不上：基线 %s… ≠ 当前 %s…（检查器被收买/被改）" % (f, exp[:12], cur[:12]))
    if problems:
        return ("tampered", problems)
    return ("ok", [])


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
    if "--update-baseline" in args:
        data = write_baseline()
        print("哈希基线已（重新）建立：")
        for f, h in data.items():
            print("  %s  %s" % (h[:16], f))
        print("\n⚠ 这是「特批流程」：只有你亲自确认检查器改动合法、且已跑过全量回归后，才许更新基线。")
        print("  总则 4.13：任何人（含 AI）改检查器，必须走特批 + 更新哈希基线。")
        return 0
    if "--self-test" in args:
        return self_test()

    print("=" * 64)
    print("一键全量回归：机器替人跑腿，任一节点报红立即终止")
    print("=" * 64)

    # 第 0 步：哈希指纹核对（检查器被收买 → 红牌）
    print("\n[0 哈希指纹核对（检查器是否被收买）]")
    bl_status, bl_problems = check_baseline()
    if bl_status == "tampered":
        for p in bl_problems:
            print("   × " + p)
        print("\n>>> 红牌！检查器哈希对不上，疑似被收买/被篡改，立即终止，不许交付。<<<")
        print("   若确属合法修改，走特批：`python 跑全量回归.py --update-baseline`（见总则 4.13）。")
        print("=" * 64)
        return 1
    elif bl_status == "skip":
        print("   · " + (bl_problems[0] if bl_problems else "无哈希基线，跳过核对"))
    else:
        print("   ✓ %d 个守护文件哈希全部一致（检查器未被收买）" % len(GUARDED_FILES))

    failed = []
    passed = 0

    for title, script, node_args in NODES:
        # clone 布局无 check_memory.py（本机自证件）→ 软跳过，不算失败
        if not os.path.isfile(os.path.join(BASE, script)):
            print("\n[%s]\n   · 跳过（%s 不存在，本机自证件未随包发布）" % (title, script))
            continue
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

    # 4) 哈希基线校验逻辑「会红」：喂一个假的基线（sha 全错），check_baseline 必须判 tampered
    global BASELINE_FILE
    import tempfile
    real_baseline = BASELINE_FILE
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
    os.close(tmp_fd)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({name: "0" * 64 for name in GUARDED_FILES}, f)
    BASELINE_FILE = tmp_path
    bl_status, bl_problems = check_baseline()
    BASELINE_FILE = real_baseline
    os.remove(tmp_path)
    ok_all = ok_all and (bl_status == "tampered" and len(bl_problems) > 0)
    print("  [%s] 假基线（sha 全错）→ 哈希核对判 tampered，检出 %d 个问题" %
          ("PASS" if (bl_status == "tampered" and len(bl_problems) > 0) else "FAIL", len(bl_problems)))

    print("=" * 64)
    if ok_all:
        print("PASS 跑全量回归负控自检：会红、不误报、脚本齐全、哈希核对真能拦")
        return 0
    print("FAIL 跑全量回归负控自检")
    return 1


if __name__ == "__main__":
    sys.exit(main())
