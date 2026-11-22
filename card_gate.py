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
    G9  强制测试驱动：写了二级测试命令的项目，台账 decisions 里必须有一条
        格式合规的「首跑红 YYYY-MM-DD｜FAIL n｜<测试标识>」记录（总则 4.8）。
        缺、或格式不合规（假日期 / 无 FAIL n / 无测试标识）→ 判红。
        写了测试命令就不许豁免（总则 4.4：豁免前提是「本来没有」，不是「写了但没做」）。
        同时校验 decisions 里声明 verified 的修 bug 记录必须附测试输出证据（PASS n 且 FAIL 0）。

退出码: 0 全通过 / 1 有不通过项 / 2 无法检测（文件缺失等）

局限（明写，别当它能判语义）:
    G2 只能判「非空、非占位、非纯空话」，判不出失败表现是否真的可观察。
    G6 只校验测试目标文件是否存在，不执行命令、不校验解释器——能不能跑通由封版流程负责。
    G6 解析的是命令里的字面路径，相对卡所在目录；用变量拼出来的路径它看不懂，会判「定位不到」。
    G7 只判「名字对得上」，判不出那条测试是否真的在验这条验收——断言写得对不对仍要人看。
    G9 判「首跑红记录格式是否合规」（日期/FAIL n/测试标识三要素齐全），并判 verified
        声明是否附测试证据；但不执行测试、不判证据的 PASS/FAIL 数字本身是真是假——
        数字真假仍要人看（和 G7 同一层局限）。
"""
import json
import os
import re
import sys
import datetime as _dt

PLACEHOLDER = ("待定",)
G3_WORDS = ("按需", "灵活", "通常", "一般", "适当")
STATUS_RE = re.compile(r"^(P-\d{2}-[A-Za-z0-9_\-]+)｜基线 (.+?)｜待办 (\d+)｜待定 (\d+)\s*$")
HEAD_RE = re.compile(r"^## (\d+)\s")
EMPTY_TALK_RE = re.compile(r"^[\s（(]*(失败|异常|报错|有问题|不正常|表现异常|无|暂无)[\s。）)]*$")

# 二级测试：命令特征 + 豁免声明
# TEST_HINT 要能识别「运行：python ...」「二级测试：python ...」「测试：pytest ...」等
# 各种前缀写法，核心是命令里含可执行特征（解释器 + 测试入口 / --test / --selftest / pytest）。
TEST_HINT = re.compile(r"(--selftest\b|--test\b|tests[\\/]+run_tests\.py|\bpytest\b|\bpython\b|\bpython3\b)", re.I)
WAIVER_RE = re.compile(r"^[-*]?\s*二级闸门(?:豁免)?[：:]\s*(\S.*)$")

# 命令前缀：第 8 段里写在真正命令前的标签，如「运行」「二级测试」「二级闸门」「测试命令」等
CMD_PREFIX_RE = re.compile(
    r"^[\s\-*`>]*"
    r"(?:二级(?:测试|闸门)|测试命令|测试|运行命令|运行|执行|命令|跑)[：:]\s*"
    r"|^[\s\-*`>]*(?:二级(?:测试|闸门)|测试命令|运行命令|运行|执行)[\s：:]+",
    re.I)

# G9：首跑红记录格式（总则 4.8 第 3 步）：首跑红 YYYY-MM-DD｜FAIL n｜<测试标识列表>
# 必须带具体日期（YYYY-MM-DD）、FAIL n（n≥1）、以及至少一个非空测试标识。
FIRST_RED_RE = re.compile(r"首跑红\s+(\d{4}-\d{2}-\d{2})\s*[｜|]\s*FAIL\s+([1-9]\d*)\s*[｜|]\s*(\S+)")

# G9：verified 证据 —— 修 bug 声明 verified 必须附「PASS n 且 FAIL 0」（总则 4.11）。
VERIFIED_EVIDENCE_RE = re.compile(r"verified", re.I)
PASS_FAIL_OK_RE = re.compile(r"PASS\s+[1-9]\d*\b.*\bFAIL\s+0\b|FAIL\s+0\b.*\bPASS\s+[1-9]\d*\b")


def extract_command(raw):
    """从第 8 段的一行里提取真正的可执行命令。

    识别并剥离各种前缀标签（运行 / 二级测试 / 二级闸门 / 测试命令 / 测试 / 执行 等），
    返回干净的「解释器 + 参数」字符串。剥不掉前缀则原样返回（去首尾空白与列表符号）。
    """
    s = raw.strip().lstrip("-* `>").strip()
    # 1) 先尝试用前缀正则剥离（「运行：python ...」「二级测试：python ...」）
    m = CMD_PREFIX_RE.match(s)
    if m:
        s = s[m.end():].strip()
        s = s.lstrip("-* `>").strip()
    # 2) 若剥完仍以中文标签开头（如「运行 python tests」无冒号），再按常见标签硬切一次
    for label in ("二级测试", "二级闸门", "测试命令", "运行命令", "运行", "执行"):
        if s.startswith(label):
            rest = s[len(label):].lstrip("：: -").strip()
            if rest:
                s = rest
                break
    return s


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


def seal_archive(card_id, version, base_dir, test_summary=None, acc_rows=None):
    """封版通过后写归档摘要到 <base_dir>/_归档/YYYYMMDD-vX.md。

    base_dir 用脚本所在目录动态定位（不用盘符硬编码，正本与 clone 都能跑）。
    归档只记录「旧版指标」，作为回滚对比的基准；不覆盖已有同名文件（同日重复封版按序号递增）。

    test_summary: 二级测试的真实回执字符串（如「PASS 3 / FAIL 0」，实际执行所得，非占位）。
    acc_rows: 第 9 段验收表的真实行（逐条回填可用功能/验收口径，非「见项目卡」空话）。
    """
    archive_dir = os.path.join(base_dir, "_归档")
    os.makedirs(archive_dir, exist_ok=True)
    stamp = _dt.datetime.now()
    date = stamp.strftime("%Y%m%d")
    # 同日多次封版：vX 序号递增，找当天已存在的最大序号 +1
    import glob
    existing = glob.glob(os.path.join(archive_dir, f"{date}-*.md"))
    seq = 1
    if existing:
        nums = []
        for p in existing:
            m = re.search(r"-v(\d+)\.md$", os.path.basename(p))
            if m:
                nums.append(int(m.group(1)))
        seq = max(nums) + 1 if nums else 1
    # 版本号优先用调用方给的，否则用序号 vN
    ver = version if version else f"v{seq}"
    fname = f"{date}-{ver}.md"
    path = os.path.join(archive_dir, fname)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# 封版归档 {card_id} · {ver}\n\n")
        f.write(f"- 封版时间：{stamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 卡号：{card_id}\n")
        f.write(f"- 版本号：{ver}\n")
        f.write(f"- 归档目的：记录旧版指标，作为回滚对比基准（只读）\n\n")
        f.write("## 旧版指标\n\n")
        if acc_rows:
            f.write("### 验收口径（第 9 段逐条）\n\n")
            for i, cells in enumerate(acc_rows, 1):
                # 第 9 段列序：编号 | 动作 | 期望结果 | 失败表现 | 测试标识
                action = cells[1] if len(cells) > 1 else ""
                expect = cells[2] if len(cells) > 2 else ""
                f.write("- %d. %s → 期望 %s\n" % (i, action, expect))
            f.write("\n")
        else:
            f.write("- 验收口径：见项目卡第 9 段「验收」表\n\n")
        if test_summary:
            f.write(f"### 二级测试（真实回执）\n\n- {test_summary}\n\n")
        else:
            f.write("- 二级测试：未执行（本次封版未跑二级命令）\n\n")
        f.write("> 本文件由 `card_gate.py --seal` 生成。索引同步由封版动作另行更新。\n")
    return path


def run_secondary_test(cmd, base):
    """实际执行第 8 段的二级测试命令，返回 (exit_code, 输出全文)。

    从输出里抓 PASS/FAIL 数字。命令相对卡所在目录（base）执行。
    先用 extract_command 剥离各种前缀（运行/二级测试/测试命令等），再切分执行。
    """
    import subprocess
    clean = extract_command(cmd)
    parts = clean.split()
    if not parts:
        return None, ""
    try:
        p = subprocess.run(parts, cwd=base, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out
    except FileNotFoundError:
        return None, "解释器不存在：%s" % parts[0]
    except subprocess.TimeoutExpired:
        return None, "二级测试执行超时（>120s）"
    except OSError as e:
        return None, "二级测试执行失败：%s" % e


def parse_pass_fail(text):
    """从测试输出里解析 PASS n / FAIL m 数字。找不到返回 (None, None)。"""
    p = re.search(r"\bPASS\s+(\d+)\b", text, re.I)
    f = re.search(r"\bFAIL\s+(\d+)\b", text, re.I)
    return (int(p.group(1)) if p else None,
            int(f.group(1)) if f else None)


def update_index(card_id, version, index_path):
    """同步更新 索引.md 里该卡的状态行：只改「状态」列和「最后变更日」列，绝不碰「基线」列。

    用表头列名精确定位列位置（不是模糊匹配状态词），避免把基线列里
    「v0（未封版）」的「封版」字样误当状态改掉。
    只改该卡那一个表格行，不删不改其它行（遵守追加区纪律）。
    找不到该卡行或表头 → 静默返回 None（不改动索引）。
    """
    if not os.path.isfile(index_path):
        return None
    with open(index_path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    # 1) 先定位表头行，解析「状态」「最后变更日」两列的列下标
    header_idx = None
    col_status = col_date = None
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("|"):
            continue
        cells = split_row(ln)
        if not cells:
            continue
        # 表头特征：含「卡号」列（数据行第一列是 P-xx 卡号，不会是「卡号」二字）
        if cells[0].strip() in ("卡号", "卡ID", "编号"):
            header_idx = i
            for j, c in enumerate(cells):
                c = c.strip()
                if c in ("状态", "进度", "state"):
                    col_status = j
                elif c in ("最后变更日", "最后变更", "日期", "更新日", "date"):
                    col_date = j
            break
    if header_idx is None or col_status is None:
        return None  # 找不到表头或没有「状态」列，无法安全定位，宁可不改

    # 2) 找该卡的数据行，按列下标精确改「状态」和「日期」，绝不碰其它列
    stamp = _dt.datetime.now().strftime("%Y-%m-%d")
    changed = False
    for i, ln in enumerate(lines):
        if i <= header_idx:
            continue
        if not ln.strip().startswith("|"):
            continue
        cells = split_row(ln)
        if not cells or cells[0].strip() != card_id:
            continue
        new_cells = list(cells)
        # 状态列 → 已封版 <version>
        if col_status < len(new_cells) and new_cells[col_status].strip() != ("已封版 " + version):
            new_cells[col_status] = "已封版 " + version
            changed = True
        # 日期列 → 今天（仅当该列存在且是日期形）
        if col_date is not None and col_date < len(new_cells):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", new_cells[col_date].strip()):
                if new_cells[col_date].strip() != stamp:
                    new_cells[col_date] = stamp
                    changed = True
        if changed:
            lines[i] = "| " + " | ".join(new_cells) + " |"
        break
    if changed:
        with open(index_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    return index_path if changed else None


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
        print("用法: python card_gate.py <项目卡.md> [--ledger <_台账.json>] [--seal <版本号>]")
        return 2
    card = sys.argv[1]
    ledger_path = None
    seal_ver = None
    if "--ledger" in sys.argv:
        ledger_path = sys.argv[sys.argv.index("--ledger") + 1]
    if "--seal" in sys.argv:
        i = sys.argv.index("--seal")
        if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
            seal_ver = sys.argv[i + 1]
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
            # 存「剥离前缀后的干净命令」，G6 定位目标、G7、归档执行都用它
            hit8 = extract_command(s.lstrip("-* ").strip())
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

    # G9：强制测试驱动 —— 写了二级测试命令的项目，台账 decisions 必须有一条格式合规的
    # 「首跑红 YYYY-MM-DD｜FAIL n｜<测试标识>」记录（正则校验，不是子串匹配）。
    # 写了测试命令就不许豁免（总则 4.4：豁免前提是「本来没有」）。
    # 同时校验 decisions 里声明 verified 的修 bug 记录必须附测试输出证据。
    if hit8:
        if not os.path.isfile(ledger_path):
            results.append(("G9", False, "台账缺失，无法核验首跑红记录 -> %s" % ledger_path))
        else:
            try:
                with open(ledger_path, encoding="utf-8") as f:
                    led9 = json.load(f)
                decisions = [d for d in led9.get("decisions", []) if isinstance(d, str)]

                # 虎1：首跑红必须格式合规（正则），子串匹配不算
                first_red_ok = [d for d in decisions if FIRST_RED_RE.search(d)]
                first_red_fake = [d for d in decisions
                                  if "首跑红" in d and not FIRST_RED_RE.search(d)]

                # 虎3：verified 声明必须附测试证据（PASS n 且 FAIL 0）
                bad_verified = [d for d in decisions
                                if VERIFIED_EVIDENCE_RE.search(d)
                                and not PASS_FAIL_OK_RE.search(d)]

                problems = []
                if not first_red_ok:
                    if first_red_fake:
                        problems.append(
                            "有「首跑红」字样但格式不合规（缺具体日期/FAIL n/测试标识）：%s" %
                            first_red_fake[0][:60])
                    problems.append(
                        "写了二级测试命令，但台账 decisions 没有格式合规的「首跑红 YYYY-MM-DD｜FAIL n｜<测试标识>」记录。"
                        "总则 4.8：任何涉及逻辑的业务代码修改，必须先写测试、跑红留证才许写业务代码。缺此记录，封版判红。")
                if bad_verified:
                    problems.append(
                        "decisions 里有声明 verified 但未附测试输出证据（须 PASS n 且 FAIL 0）的记录：%s" %
                        bad_verified[0][:60])

                if problems:
                    results.append(("G9", False, "；".join(problems)))
                else:
                    results.append(("G9", True,
                        "首跑红记录格式合规（%d 条），verified 声明均附测试证据" % len(first_red_ok)))
            except json.JSONDecodeError as e:
                results.append(("G9", False, "台账 JSON 解析失败：%s" % e))
    else:
        # 没写二级测试命令（G6 已判红，或已豁免），G9 不重复卡
        results.append(("G9", True, "未写二级测试命令，不强制首跑红"))

    # 输出
    card_id = status.group(1) if status else os.path.basename(card)
    print("card_gate｜%s" % card_id)
    for cid, ok, detail in results:
        print("%s %s｜%s" % (cid, "通过" if ok else "不通过", detail))
    passed = sum(1 for _, ok, _ in results if ok)
    verdict = "通过" if passed == len(results) else "不通过"
    print("结论：%s（%d/%d）" % (verdict, passed, len(results)))

    # 封版归档：全绿且带 --seal 时，实际执行二级测试拿真实数字，写归档摘要 + 同步索引
    if verdict == "通过" and seal_ver is not None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # 1) 真实执行二级测试命令（hit8 已在 G6 解析过），回填 PASS/FAIL 数字
        test_summary = None
        if hit8:
            rc, out = run_secondary_test(hit8, base)
            pn, fn = parse_pass_fail(out)
            if pn is not None or fn is not None:
                test_summary = "`%s` → 退出码 %s，PASS %s / FAIL %s（%s）" % (
                    hit8[:48], rc if rc is not None else "?",
                    pn if pn is not None else 0,
                    fn if fn is not None else 0,
                    _dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
            else:
                test_summary = "`%s` → 退出码 %s（输出未见 PASS/FAIL 数字，见回执）" % (
                    hit8[:48], rc if rc is not None else "?")
        # 2) 回填验收口径（第 9 段真实行）
        acc_rows = table_rows(sec.get(9, (0, []))[1])
        ap = seal_archive(card_id, seal_ver, base_dir, test_summary=test_summary,
                          acc_rows=acc_rows)
        print("归档：已生成 %s" % ap)
        # 3) 同步索引（状态→已封版 vX，基线日期→今天）
        index_path = os.path.join(base_dir, "索引.md")
        ip = update_index(card_id, seal_ver, index_path)
        if ip:
            print("索引：已更新 %s 的封版状态" % card_id)
        else:
            print("索引：未找到 %s 对应行（或索引.md 不存在），跳过" % card_id)

    return 0 if verdict == "通过" else 1


if __name__ == "__main__":
    sys.exit(main())
