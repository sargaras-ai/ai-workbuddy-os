#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""开卡.py —— 《项目》 <短名> 的机械化开卡器（仅标准库，py3.6+ 可跑）

用法：
    python H:\\项目约束包\\开卡.py P-03-invoice
    python H:\\项目约束包\\开卡.py P-03-invoice --dry-run
    python H:\\项目约束包\\开卡.py --self-test          # 自检：全在临时目录，不碰真索引

包目录与新项目根目录默认按脚本所在位置推导（可用环境变量覆盖，换机/换盘不必改源码）：
    WB_PACK  P-00-空白卡 / 索引 / card_gate 所在目录，默认 = 脚本所在目录
    WB_ROOT  新项目目录建在这下面，默认 = 包目录的上一级

做的事（顺序固定，不可调换）：
    1 校验短名格式        P-XX-short（两位序号 + 小写英文/数字/连字符）
    2 查重                索引已有该卡号 → 中止；<根目录>\\<短名>\\ 已存在 → 中止
    3 建目录              <根目录>\\<短名>\\
    4 复制空白卡          P-00-空白卡.md → 项目卡.md，替换卡号/状态行/根路径/自检命令
    4.5 锁                卡第 8 段若已写二级测试命令，其目标必须真实存在，否则中止并回滚
    5 写台账              _台账.json，card + updated + 四个空数组
    6 追加索引            索引.md 末行追加（项目名写「待定」，开卡时还没定位）
    7 跑闸门              card_gate.py，报结果

失败处理：4-7 任一步失败 → 删掉本次刚建的目录、删掉本次刚追加的索引行，回执「已回滚」。
          只删自己建的，不动任何既有文件。

开卡闸门预期：G1/G3/G5 应通过；G2/G4/G6 必红（验收、待定项、二级测试命令还是占位）。
             这是「空卡态」的正常结果，不是错误，脚本会单独标注。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

BASE = os.environ.get("WB_PACK") or os.path.dirname(os.path.abspath(__file__))
ROOT_BASE = os.environ.get("WB_ROOT") or os.path.dirname(BASE)
BLANK = os.path.join(BASE, "P-00-空白卡.md")
INDEX = os.path.join(BASE, "索引.md")
GATE = os.path.join(BASE, "card_gate.py")

sys.path.insert(0, BASE)
import card_gate  # noqa: E402  复用 G6 的路径解析，避免「闸门一套、开卡器另一套」

NAME_RE = re.compile(r"^P-(\d{2})-([a-z][a-z0-9-]{1,20})$")


class GateStructureError(Exception):
    """开卡器产出的卡结构不合格（不是占位预期）——必须中止并回滚。"""


def check_card_test_target(card_path):
    """卡第 8 段若写了二级测试命令，校验其目标真实存在。有问题返回文本；没问题返回 None。

    与 card_gate 的 G6 共用 find_test_target / target_path，
    避免「闸门判红、开卡器判绿」两套标准。
    """
    try:
        with open(card_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r"^##\s*8\s.*?$(.*?)(?=^##\s*9\s)", text, re.M | re.S)
    block = m.group(1) if m else ""
    base = os.path.dirname(os.path.abspath(card_path))
    for ln in block.splitlines():
        s = ln.strip()
        if not s or "待定" in s or "占位" in s:
            continue
        if not card_gate.TEST_HINT.search(s):
            continue
        tgt = card_gate.find_test_target(s)
        if not tgt:
            return ("第 8 段二级测试命令定位不到目标路径：%s"
                    "（请写明 tests/run_tests.py、被测 .py 或 tests 目录）" % s[:60])
        p = card_gate.target_path(base, tgt)
        if not os.path.exists(p):
            return "第 8 段声明的测试目标不存在：%s（解析为 %s）" % (tgt, p)
    return None


def gate_structure_bad(out):
    """结构项 G1/G3/G5 未通过的清单与明细。空清单＝全绿。

    只认闸门回执行「G1 通过｜…」；缺行按「缺失」算不通过
    （闸门自己崩掉时不能当结构没问题）。
    """
    seen = {}
    for ln in out.splitlines():
        m = re.match(r"^(G\d) (通过|不通过)｜", ln)
        if m:
            seen[m.group(1)] = m.group(2)
    bad = [g for g in ("G1", "G3", "G5") if seen.get(g) != "通过"]
    detail = "；".join("%s=%s" % (g, seen.get(g, "缺失")) for g in bad)
    return bad, detail


def fail(msg, code=2):
    print("开卡 中止｜" + msg)
    sys.exit(code)


def check_name(name):
    m = NAME_RE.match(name or "")
    if not m:
        fail("短名格式非法：%r｜要求 P-两位序号-小写英文短名（如 P-03-invoice），"
             "不许中文、空格、大写" % (name,))
    return m.group(1), m.group(2)


def read_index(index_path):
    if not os.path.isfile(index_path):
        fail("索引不存在：%s（先建索引再开卡）" % index_path)
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()


def index_has(text, card):
    # 只认表格首列，避免子串误判（P-03-inv 不会命中 P-03-invoice）
    for ln in text.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and cells[0] == card:
            return True
    return False


def render_card(blank_text, card, root):
    t = blank_text
    t = t.replace("P-00-blank｜基线 v0（未封版）｜待办 0｜待定 0",
                  "%s｜基线 v0（未封版）｜待办 0｜待定 0" % card)
    t = t.replace("# P-00 空白卡", "# %s（项目名待定）" % card)
    t = t.replace("## 1 卡号\nP-00-blank", "## 1 卡号\n%s" % card)
    # 已知值当场填，不留占位：根路径与自检命令开卡即确定
    t = t.replace("- 根：待定", "- 根：`%s`" % root)
    t = t.replace("- 自检：待定",
                  "- 自检：`python %s %s`" % (GATE, os.path.join(root, "项目卡.md")))
    return t


def ledger_json(card, today):
    return json.dumps({
        "card": card,
        "updated": today,
        "decisions": [],
        "tasks": [],
        "unknowns": [],
        "pits": [],
    }, ensure_ascii=False, indent=2) + "\n"


def append_index(index_path, old_text, row):
    sep = "" if old_text.endswith("\n") else "\n"
    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(old_text + sep + row + "\n")


def rollback_index(index_path, old_text):
    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(old_text)


def run_gate(card_path):
    try:
        p = subprocess.Popen([sys.executable, GATE, card_path],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.communicate()[0].decode("utf-8", "replace")
        return p.returncode, out
    except Exception as e:  # 闸门自身跑不起来，不能当成卡没问题
        return 99, "GATE_ERROR: %s" % e


def open_card(card, root, base_dir, index_path, dry_run=False):
    num, short = check_name(card)
    today = datetime.now().strftime("%Y-%m-%d")

    idx_text = read_index(index_path)
    if index_has(idx_text, card):
        fail("索引里已有卡号 %s，不覆盖。要改旧卡用落盘/切到，不重开" % card)
    if os.path.exists(root):
        fail("目录已存在：%s，不覆盖（哪怕空目录也停手，可能是上次失败的残留，"
             "确认后手工删掉再开）" % root)
    if dry_run:
        print("开卡 DRY-RUN｜校验通过，未写任何文件｜卡号 %s｜根目录 %s" % (card, root))
        return 0

    created_dir = False
    index_written = False
    try:
        os.makedirs(root)
        created_dir = True

        with open(BLANK, "r", encoding="utf-8") as f:
            blank = f.read()
        card_path = os.path.join(root, "项目卡.md")
        with open(card_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_card(blank, card, root))

        # 锁：卡里若已写二级测试命令，其目标必须真实存在（写了不存在的路径＝伪造，直接中止+回滚）
        bad_target = check_card_test_target(card_path)
        if bad_target:
            raise GateStructureError("测试目标校验未通过——" + bad_target)

        with open(os.path.join(root, "_台账.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(ledger_json(card, today))

        row = "| %s | 待定 | `%s` | v0（未封版） | 在建 | %s |" % (card, root, today)
        append_index(index_path, idx_text, row)
        index_written = True

        code, out = run_gate(card_path)
        print("已开卡：%s｜根目录：%s" % (card, root))
        print("台账：_台账.json（4 数组空）｜索引：末行已追加｜闸门退出码：%s" % code)
        print("")
        print(out.rstrip())

        # 结构项必须全绿：G1/G3/G5 任一不是「通过」= 卡结构坏了，不属于占位预期，绝不能报成"预期"
        bad, detail = gate_structure_bad(out)
        if bad:
            raise GateStructureError(
                "闸门结构项 %s 未通过（预期只有 G2/G4/G6 可为红）：%s" % ("/".join(bad), detail))

        if code == 0:
            print("闸门 6/6 —— 卡已可直接填内容。")
        else:
            print("闸门非满分属预期：G2/G4/G6 红是「空卡占位态」的正常结果（验收、待定项、二级测试命令还没填）。")
            print("判据：G1/G3/G5 必须通过（已机器校验）；G2/G4/G6 转绿要等你给定位/目标/验收/二级测试命令。")
        print("")
        print("请告诉我项目定位/目标/非目标。")
        return 0
    except GateStructureError as e:
        # 结构不合格：与写盘失败同等处理，回滚干净，退出码 1
        if index_written:
            rollback_index(index_path, idx_text)
            print("回滚：索引末行已撤销")
        if created_dir and os.path.isdir(root):
            shutil.rmtree(root, ignore_errors=True)
            print("回滚：目录 %s 已删除" % root)
        fail("开卡中止｜卡结构不合格 —— %s。已回滚，磁盘未留半成品" % e, 1)
    except Exception as e:
        # 回滚：只撤本次做的
        if index_written:
            rollback_index(index_path, idx_text)
            print("回滚：索引末行已撤销")
        if created_dir and os.path.isdir(root):
            shutil.rmtree(root, ignore_errors=True)
            print("回滚：目录 %s 已删除" % root)
        fail("写入过程失败（%s: %s），已回滚，磁盘未留半成品" % (type(e).__name__, e), 1)


def self_test():
    """全程在临时目录跑，不碰 H:\\ 根与真索引。"""
    tmp = tempfile.mkdtemp(prefix="kaika_selftest_")
    base = os.path.join(tmp, "包")
    os.makedirs(base)
    shutil.copy(BLANK, os.path.join(base, "P-00-空白卡.md"))
    idx = os.path.join(base, "索引.md")
    with open(idx, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 索引\n\n| 卡号 | 项目名 | 根路径 | 基线 | 状态 | 最后变更日 |\n"
                "|---|---|---|---|---|---|\n| P-01-hede | 禾灯 | `H:\\P01-hede\\` | v1.0 | 在建 | 2026-11-15 |\n")

    ok = True

    # 1 非法名
    for bad in ["project3", "P-3-x", "P-03-Invoice", "P-03-发票", "P-03-"]:
        if NAME_RE.match(bad):
            print("SELFTEST FAIL｜非法名被放过：%r" % bad); ok = False
    print("S1 非法名拒绝            :", ok)

    # 2 正常开卡（沙盒）
    root = os.path.join(tmp, "P-03-invoice")
    r = open_card("P-03-invoice", root, base, idx)
    card_path = os.path.join(root, "项目卡.md")
    t = open(card_path, encoding="utf-8").read()
    d = json.load(open(os.path.join(root, "_台账.json"), encoding="utf-8"))
    c1 = t.splitlines()[3].strip() == "P-03-invoice｜基线 v0（未封版）｜待办 0｜待定 0"
    c2 = "## 1 卡号\nP-03-invoice" in t
    c3 = "P-00" not in t
    c4 = d["card"] == "P-03-invoice" and d["decisions"] == [] and len(d["tasks"]) == 0
    c5 = index_has(open(idx, encoding="utf-8").read(), "P-03-invoice")
    print("S2 状态行替换            :", c1)
    print("S3 卡号段落替换          :", c2)
    print("S4 无 P-00 残留          :", c3)
    print("S5 台账结构              :", c4)
    print("S6 索引追加              :", c5)
    ok = ok and all([c1, c2, c3, c4, c5])

    # 3 重名保护
    idx_before = open(idx, encoding="utf-8").read()
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "P-03-invoice",
                          "--root", root, "--index", idx],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.communicate()[0].decode("utf-8", "replace")
    c6 = (p.returncode != 0 and "中止" in out and
          open(idx, encoding="utf-8").read() == idx_before)
    print("S7 重名/已建目录 中止且不改索引:", c6, "|", out.strip().splitlines()[0][:40])
    ok = ok and c6

    # 4 回滚：索引不可写时，目录必须被撤掉
    root2 = os.path.join(tmp, "P-04-rollback")
    idx2 = os.path.join(tmp, "索引_副本.md")
    shutil.copy(idx, idx2)
    os.chmod(idx2, 0o444)
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "P-04-rollback",
                          "--root", root2, "--index", idx2],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out2 = p.communicate()[0].decode("utf-8", "replace")
    os.chmod(idx2, 0o644)
    rolled = (not os.path.exists(root2))
    print("S8 写索引失败→目录已回滚  :", rolled, "|", out2.strip().splitlines()[:2])
    ok = ok and rolled

    # 5 锁：模板里预填了不存在的测试路径 → 必须中止并回滚（防「伪造测试」）
    fake_pack = os.path.join(tmp, "假包")
    os.makedirs(fake_pack)
    shutil.copy(GATE, os.path.join(fake_pack, "card_gate.py"))
    with open(os.path.join(fake_pack, "索引.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# 索引\n\n| 卡号 | 项目名 | 根路径 | 基线 | 状态 | 最后变更日 |\n"
                "|---|---|---|---|---|---|\n")
    src_lines = open(BLANK, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(src_lines):
        if "业务测试" in ln and "待定" in ln:
            src_lines[i] = "- 业务测试（二级）：python tests/run_tests.py"
    with open(os.path.join(fake_pack, "P-00-空白卡.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(src_lines) + "\n")

    root3 = os.path.join(tmp, "P-09-fake")
    idx3 = os.path.join(fake_pack, "索引.md")
    env3 = dict(os.environ, WB_PACK=fake_pack)
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "P-09-fake",
                          "--root", root3, "--index", idx3],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env3)
    out3 = p.communicate()[0].decode("utf-8", "replace")
    c8 = (p.returncode != 0 and "不存在" in out3 and not os.path.exists(root3))
    print("S9 假测试路径→中止并回滚  :", c8, "|", (out3.strip().splitlines() or [""])[0][:60])
    ok = ok and c8

    shutil.rmtree(tmp, ignore_errors=True)
    print("")
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in argv
    root = None
    index_path = INDEX
    for i, a in enumerate(argv):
        if a == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            if root in args:
                args.remove(root)
        if a == "--index" and i + 1 < len(argv):
            index_path = argv[i + 1]
            if index_path in args:
                args.remove(index_path)
    if not args:
        print(__doc__)
        return 2
    card = args[0].strip()
    if root is None:
        root = os.path.join(ROOT_BASE, card + "\\")
    return open_card(card, root, BASE, index_path, dry_run=dry)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
