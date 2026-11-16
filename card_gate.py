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
    G6  第 8 段含二级测试命令，且其目标（run_tests.py / 被测 .py / tests 目录）
        必须真实存在；或第 10 段声明豁免/历史卡。写了不存在的路径＝伪造测试，判红。
    G7  验收↔测试映射：第 9 段每行第 5 列须写测试标识，一条对一个、不许重复，
        且该标识要能在 G6 定位到的测试文件里逐字找到；豁免/历史卡可不填。

退出码: 0 全通过 / 1 有不通过项 / 2 无法检测（文件缺失等）

局限（明写，别当它能判语义）:
    G2 只能判「非空、非占位、非纯空话」，判不出失败表现是否真的可观察。
    G6 只校验测试目标文件是否存在，不执行命令、不校验解释器——能不能跑通由封版流程负责。
    G6 解析的是命令里的字面路径，相对卡所在目录；用变量拼出来的路径它看不懂，会判「定位不到」。
    G7 只判「名字对得上」，判不出那条测试是否真的在验这条验收——断言写得对不对仍要人看。
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

# 二级测试：命令特征 + 豁免声明
TEST_HINT = re.compile(r"(--selftest\b|--test\b|tests[\\/]+run_tests\.py)", re.I)
WAIVER_RE = re.compile(r"^[-*]?\s*二级闸门(?:豁免)?[：:]\s*(\S.*)$")


def find_test_target(cmd):
    """从二级测试命令里取出「必须真实存在」的目标路径；取不到返回 None。

    只取测试目标（run_tests.py / 被测 .py / tests 目录），不取解释器：
    解释器缺了会在封版真跑时由退出码暴露；测试文件不存在属于「伪造测试」，性质不同。
    """
    m = re.search(r"((?:[\w.\-]+[\\/])*tests[\\/]+run_tests\.py)", cmd, re.I)
    if m:
        return m.group(1)
    if re.search(r"--selftest\b|--test\b", cmd, re.I):
        m = re.search(r"([\w.\-]+(?:[\\/][\w.\-]+)*\.py)", cmd)
        if m:
            return m.group(1)
        return None
    if re.search(r"\bpytest\b", cmd, re.I):
        m = re.search(r"\btests[\\/]?\b", cmd)
        if m:
            return "tests"
    return None


def target_path(base, rel):
    """把命令里的路径按「相对卡所在目录」解析成绝对路径。"""
    p = rel.replace("\\", os.sep).replace("/", os.sep)
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


# G7 用：验收第 5 列里这些值等于没写
ID_JUNK = {"", "-", "—", "同上", "见测试", "见上", "待定", "无", "tbd", "n/a"}


def pick_test_id(cell):
    """取验收第 5 列里的测试标识：去掉反引号、开头的 → / -> 等符号、以及括注。"""
    s = (cell or "").replace("`", "").strip()
    s = re.sub(r"^[^\w]+", "", s)
    if not s:
        return ""
    return re.split(r"[\s（(，,、;；]+", s)[0].strip()


def read_test_text(path):
    """读测试目标的全部源码文本；给目录则递归取 .py。找不到返回空串。"""
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""
    buf = []
    for root, _, names in os.walk(path):
        for n in names:
            if n.endswith(".py"):
                try:
                    with open(os.path.join(root, n), encoding="utf-8", errors="replace") as f:
                        buf.append(f.read())
                except OSError:
                    pass
    return "\n".join(buf)


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

    # G6：二级测试命令写了没有 + 声明的目标是否真实存在（不执行命令）
    sec8 = sec.get(8, (0, []))[1]
    sec10 = sec.get(10, (0, []))[1]
    base = os.path.dirname(os.path.abspath(card))
    hit8, waiver = None, None
    for ln in sec8:
        s = ln.strip()
        if TEST_HINT.search(s) and "待定" not in s and "占位" not in s:
            hit8 = s.lstrip("-* ").strip()
            break
    for ln in sec10:
        m = WAIVER_RE.match(ln.strip())
        if m:
            waiver = m.group(1).strip()
            break
    waiver_ok = bool(waiver) and len(waiver) >= 6 and not re.fullmatch(r"(不适用|无|暂无)[。.]?", waiver)
    tgt, tgt_path = None, None      # 给 G7 复用：G6 定位到的测试目标

    if hit8:
        tgt = find_test_target(hit8)
        if not tgt:
            results.append(("G6", False,
                "二级测试命令定位不到目标路径，无法校验存在性：%s"
                "（请写明 tests/run_tests.py、被测 .py 或 tests 目录）" % hit8[:60]))
        else:
            p = target_path(base, tgt)
            if os.path.exists(p):
                tgt_path = p
                results.append(("G6", True, "命令组含二级测试：%s；目标存在：%s" % (hit8[:40], tgt)))
            else:
                results.append(("G6", False,
                    "伪造测试：第 8 段写的 %s 不存在（解析为 %s）。新卡无豁免权——"
                    "先建测试文件，或删掉该行改走 4.4 豁免（仅限确无业务测试的项目）" % (tgt, p)))
    elif waiver_ok:
        results.append(("G6", True, "已声明二级闸门不适用：%s" % waiver[:48]))
    else:
        results.append(("G6", False, "第 8 段缺二级测试命令（--test / --selftest / tests/run_tests.py），且第 10 段无「二级闸门豁免：<理由>」"))

    # G7：验收 ↔ 测试映射（第 9 段第 5 列；一对一；标识须在测试目标里逐字存在）
    acc9 = table_rows(sec.get(9, (0, []))[1])
    bad7, pairs, seen = [], [], {}
    for i, cells in enumerate(acc9, 1):
        tid = pick_test_id(cells[4]) if len(cells) >= 5 else ""
        if not tid or tid.lower() in ID_JUNK:
            if waiver_ok:
                continue                      # 豁免/历史卡不填映射，合法
            bad7.append("第%d条 %s" % (i, "缺第 5 列「测试标识」" if len(cells) < 5
                                       else "测试标识为空或指代不明「%s」" % (cells[4].strip() or "空")))
            continue
        if tid in seen:
            bad7.append("第%d条 与第%d条 共用同一个测试「%s」——一条验收一个测试，不许合并" % (i, seen[tid], tid))
            continue
        seen[tid] = i
        pairs.append((i, tid))

    if not acc9:
        bad7.append("第 9 段没有验收表，无从映射")
    elif pairs and not tgt_path:
        bad7.append("填了测试标识，但第 8 段没有可解析且真实存在的测试目标，无法校验（先修 G6）")
    elif pairs:
        text = read_test_text(tgt_path)
        miss = [(i, t) for i, t in pairs if t not in text]
        if miss:
            bad7.append("测试里找不到这些标识：" + "、".join("第%d条「%s」" % (i, t) for i, t in miss))

    if bad7:
        results.append(("G7", False, "；".join(bad7)))
    elif pairs:
        results.append(("G7", True, "映射 %d 条一对一，标识在 %s 里均能找到" % (len(pairs), tgt)))
    else:
        results.append(("G7", True, "已豁免/历史卡，不填映射（验收 %d 条）" % len(acc9)))

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
