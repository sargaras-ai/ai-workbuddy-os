#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""card_gate.py — 项目卡闸门（冻结件配套脚本）

用法:
    python card_gate.py <项目卡.md> [--ledger <_台账.json>]

检查项:
    G1  15 段齐全且按序（状态行不算段落）
    G2  每条验收含可观察的失败表现，且非占位
    G3  参数表无 按需/灵活/通常/一般/适当
    G4  待定项四列齐全（字段/为什么没定/谁定/决策截止日）
    G5  待定数 = 台账 unknowns 条数；状态行 待办/待定 与台账一致

退出码: 0 全通过 / 1 有不通过项 / 2 无法检测（文件缺失等）

局限（明写，别当它能判语义）:
    G2 只能判「非空、非占位、非纯空话」，判不出失败表现是否真的可观察。
"""
import json
import os
import re
import sys

PLACEHOLDER = ("待定",)
G3_WORDS = ("按需", "灵活", "通常", "一般", "适当")
STATUS_RE = re.compile(r"^(P-\d{2}-[A-Za-z0-9_\-]+)｜基线 (.+?)｜待办 (\d+)｜待定 (\d+)\s*$")
HEAD_RE = re.compile(r"^## (\d+)\s")
EMPTY_TALK_RE = re.compile(r"^[\s（(]*(失败|异常|报错|有问题|不正常|表现异常|无|暂无)[\s。）)]*$")


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_placeholder(v):
    return (not v) or any(p in v for p in PLACEHOLDER)


def sections(lines):
    """返回 {段号: (起始行, [内容行])}"""
    out, cur = {}, None
    for i, ln in enumerate(lines):
        m = HEAD_RE.match(ln)
        if m:
            cur = int(m.group(1))
            out[cur] = (i, [])
        elif cur is not None:
            out[cur][1].append(ln)
    return out


def table_rows(block):
    """取 markdown 表格数据行（跳过表头与分隔行）"""
    rows = [ln for ln in block if ln.strip().startswith("|")]
    data = []
    for r in rows:
        cells = split_row(r)
        if not cells or all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells):
            continue
        data.append(cells)
    return data[1:] if data else []


def main():
    if len(sys.argv) < 2:
        print("用法: python card_gate.py <项目卡.md> [--ledger <_台账.json>]")
        return 2
    card = sys.argv[1]
    ledger_path = None
    if "--ledger" in sys.argv:
        ledger_path = sys.argv[sys.argv.index("--ledger") + 1]
    if not os.path.isfile(card):
        print("无法检测：卡文件不存在 -> %s" % card)
        return 2
    if ledger_path is None:
        ledger_path = os.path.join(os.path.dirname(os.path.abspath(card)), "_台账.json")

    with open(card, encoding="utf-8") as f:
        lines = f.read().splitlines()
    sec = sections(lines)

    # 状态行：跳过 <!-- --> 注释块后的第一行非空
    status_line, status = None, None
    in_comment = False
    for ln in lines:
        s = ln.strip()
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("<!--"):
            if "-->" not in s:
                in_comment = True
            continue
        if not s:
            continue
        m = STATUS_RE.match(s)
        if m:
            status_line, status = s, m
        break

    results = []  # (checked_id, ok, detail)

    # G1
    nums = sorted(sec.keys())
    if nums == list(range(1, 16)) and status:
        results.append(("G1", True, "15 段齐全按序；状态行可解析"))
    elif nums != list(range(1, 16)):
        missing = [n for n in range(1, 16) if n not in nums]
        extra = [n for n in nums if n not in range(1, 16)]
        detail = "段号异常"
        if missing:
            detail += "；缺 %s" % missing
        if extra:
            detail += "；多 %s" % extra
        results.append(("G1", False, detail))
    else:
        results.append(("G1", False, "状态行缺失或格式不符：卡号｜基线 vX（YYYY-MM-DD）｜待办 N｜待定 M"))

    # G2
    acc = table_rows(sec.get(9, (0, []))[1])
    bad2 = []
    for i, cells in enumerate(acc, 1):
        v = cells[3] if len(cells) > 3 else ""
        if len(cells) < 4:
            bad2.append("第%d条 表格不足4列" % i)
        elif is_placeholder(v):
            bad2.append("第%d条 失败表现为占位「%s」" % (i, v or "空"))
        elif len(v) < 4:
            bad2.append("第%d条 失败表现过短「%s」" % (i, v))
        elif EMPTY_TALK_RE.match(v):
            bad2.append("第%d条 失败表现是空话「%s」" % (i, v))
    if not acc:
        results.append(("G2", False, "验收表为空"))
    elif bad2:
        results.append(("G2", False, "；".join(bad2)))
    else:
        results.append(("G2", True, "验收 %d 条，失败表现均非占位" % len(acc)))

    # G3
    bad3 = []
    for cells in table_rows(sec.get(11, (0, []))[1]):
        for c in cells:
            if c.startswith("待定"):
                continue
            for w in G3_WORDS:
                if w in c:
                    bad3.append("「%s」含「%s」" % (c, w))
    if bad3:
        results.append(("G3", False, "；".join(sorted(set(bad3)))))
    else:
        results.append(("G3", True, "参数表无 按需/灵活/通常/一般/适当"))

    # G4
    pend = table_rows(sec.get(14, (0, []))[1])
    bad4, real_pend = [], 0
    for i, cells in enumerate(pend, 1):
        if len(cells) < 4:
            bad4.append("第%d行 不足4列" % i)
            continue
        if cells[0].startswith("无"):
            continue
        real_pend += 1
        for j, col in enumerate(("字段", "为什么没定", "谁定", "决策截止日")):
            if is_placeholder(cells[j]):
                bad4.append("第%d行「%s」为占位" % (i, col))
    if not pend:
        results.append(("G4", False, "待定项表为空，需写一行「无」"))
    elif bad4:
        results.append(("G4", False, "；".join(bad4)))
    else:
        results.append(("G4", True, "待定 %d 条，四列齐全" % real_pend))

    # G5
    if not os.path.isfile(ledger_path):
        results.append(("G5", False, "台账缺失 -> %s" % ledger_path))
    else:
        try:
            with open(ledger_path, encoding="utf-8") as f:
                led = json.load(f)
            n_task, n_unk = len(led.get("tasks", [])), len(led.get("unknowns", []))
            if not status:
                results.append(("G5", False, "状态行不可解析，无法核对"))
            else:
                s_task, s_unk = int(status.group(3)), int(status.group(4))
                msg = []
                if s_unk != n_unk:
                    msg.append("状态行待定 %d ≠ 台账 unknowns %d" % (s_unk, n_unk))
                if s_task != n_task:
                    msg.append("状态行待办 %d ≠ 台账 tasks %d" % (s_task, n_task))
                if msg:
                    results.append(("G5", False, "；".join(msg)))
                else:
                    results.append(("G5", True, "待办 %d / 待定 %d，与台账一致（只数台账，不数卡内占位）" % (n_task, n_unk)))
        except json.JSONDecodeError as e:
            results.append(("G5", False, "台账 JSON 解析失败：%s" % e))

    # 输出
    card_id = status.group(1) if status else os.path.basename(card)
    print("card_gate｜%s" % card_id)
    for cid, ok, detail in results:
        print("%s %s｜%s" % (cid, "通过" if ok else "不通过", detail))
    passed = sum(1 for _, ok, _ in results if ok)
    verdict = "通过" if passed == len(results) else "不通过"
    print("结论：%s（%d/%d）" % (verdict, passed, len(results)))
    return 0 if verdict == "通过" else 1


if __name__ == "__main__":
    sys.exit(main())
