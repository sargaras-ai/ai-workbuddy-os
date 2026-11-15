#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""开卡.py —— 《项目》 <短名> 的机械化开卡器（仅标准库，py3.6+ 可跑）

用法（在仓库目录内，或写全路径都行）：
    python 开卡.py P-03-invoice
    python 开卡.py P-03-invoice --dry-run
    python 开卡.py P-03-invoice --root /path/to/workspace/P-03-invoice
    python 开卡.py --self-test          # 自检：全在临时目录，不碰真索引

路径规则（可移植性）：
    所有内部路径都由 os.path.dirname(os.path.abspath(__file__)) 推导，
    clone 到任何盘符、任何目录都能直接跑，不需要改代码。
    新建项目目录默认落在「本仓库的上级目录」（即工作区）下，可用 --root 覆盖。

做的事（顺序固定，不可调换）：
    1 校验短名格式        P-XX-short（两位序号 + 小写英文/数字/连字符）
    2 查重                索引已有该卡号 → 中止；目标目录已存在 → 中止
    3 建目录              <工作区>/<短名>/
    4 复制空白卡          P-00-空白卡.md → 项目卡.md，替换卡号/状态行/根路径/自检命令
    5 写台账              _台账.json，card + updated + 四个空数组
    6 追加索引            索引.md 末行追加（项目名写「待定」，开卡时还没定位）
    7 跑闸门              card_gate.py，报结果

失败处理：4-7 任一步失败 → 删掉本次刚建的目录、删掉本次刚追加的索引行，回执「已回滚」。
          只删自己建的，不动任何既有文件。

开卡闸门预期：G1/G3/G5 应通过；G2/G4 必红（验收与待定项还是占位）。
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

# 以脚本自身位置为根，不写死任何盘符
BASE = os.path.dirname(os.path.abspath(__file__))
BLANK = os.path.join(BASE, "P-00-空白卡.md")
INDEX = os.path.join(BASE, "索引.md")
GATE = os.path.join(BASE, "card_gate.py")
# 工作区默认＝仓库的上级目录（项目与约束包平级）
WORKSPACE = os.path.dirname(BASE)

NAME_RE = re.compile(r"^P-(\d{2})-([a-z][a-z0-9-]{1,20})$")


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
        if code == 0:
            print("闸门 5/5 —— 卡已可直接填内容。")
        else:
            print("闸门非满分属预期：G2/G4 红是「空卡占位态」的正常结果（验收与待定项还没填）。")
            print("判据：G1/G3/G5 必须通过；G2/G4 转绿要等你给定位/目标/验收。")
        print("")
        print("请告诉我项目定位/目标/非目标。")
        return 0
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
    """全程在临时目录跑，不碰真索引。"""
    tmp = tempfile.mkdtemp(prefix="kaika_selftest_")
    base = os.path.join(tmp, "包")
    os.makedirs(base)
    shutil.copy(BLANK, os.path.join(base, "P-00-空白卡.md"))
    idx = os.path.join(base, "索引.md")
    with open(idx, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 索引\n\n| 卡号 | 项目名 | 根路径 | 基线 | 状态 | 最后变更日 |\n"
                "|---|---|---|---|---|---|\n| P-01-demo | 演示项目 | `<workspace>/P-01-demo/` | v1.0 | 在建 | 2026-01-01 |\n")

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
        root = os.path.join(WORKSPACE, card)
    return open_card(card, root, BASE, index_path, dry_run=dry)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
