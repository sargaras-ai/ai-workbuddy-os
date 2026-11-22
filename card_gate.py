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
import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
import datetime as _dt

PLACEHOLDER = ("待定",)
G3_WORDS = ("按需", "灵活", "通常", "一般", "适当")
STATUS_RE = re.compile(r"^(P-\d{2}-[A-Za-z0-9_\-]+)｜基线 (.+?)｜待办 (\d+)｜待定 (\d+)\s*$")
HEAD_RE = re.compile(r"^## (\d+)\s")
EMPTY_TALK_RE = re.compile(r"^[\s（(]*(失败|异常|报错|有问题|不正常|表现异常|无|暂无)[\s。）)]*$")

# 二级测试：命令特征 + 豁免声明
# TEST_HINT 要能识别「运行：python ...」「二级测试：python ...」「业务测试（二级）：python ...」
# 等各种前缀写法，核心是命令里含可执行特征（解释器 + 测试入口 / --test / --selftest / pytest）。
TEST_HINT = re.compile(r"(--selftest\b|--test\b|tests[\\/]+run_tests\.py|\bpytest\b|\bpython\b|\bpython3\b)", re.I)
WAIVER_RE = re.compile(r"^[-*]?\s*二级闸门(?:豁免)?[：:]\s*(\S.*)$")

# 命令前缀标签：第 8 段写在真正命令前的各种标签写法。
# 覆盖中文：运行 / 二级测试 / 二级闸门 / 业务测试（二级）/ 测试命令 / 测试 / 执行 / 命令 / 跑
#       英文：run / test / exec / execute
# 前缀可能被 [ ]、【 】、（ ）包裹，如「[二级测试]」「【运行】」；也可能带「（二级）」修饰；
# 行首可能是列表符号「- * 1) 1. ①」等序号。用 | 拼接成一个大标签分支。
_CMD_LABEL = (r"(?:二级(?:测试|闸门)|业务测试|测试命令|运行命令|运行|执行|命令|测试|跑"
              r"|说明|备注|run|test|exec|execute)")
# 行首杂项：空白 + 列表符(- * > ·) + 可选序号(1) 1. ① 一、) + 可选的 []【】（）() 包裹
_LINE_PRE = (r"^[\s\-*`>·]*"
             r"(?:\(\d+\)|（\d+）|\d+[\.、)]|[①②③④⑤⑥⑦⑧⑨⑩]|[一二三四五六七八九十]+[、.])?\s*"
             r"[\[【（(]?\s*")
# 冒号形式：「运行：」「[二级测试]：」「业务测试（二级）：」「RUN:」等
CMD_PREFIX_RE = re.compile(
    _LINE_PRE + _CMD_LABEL + r"\s*(?:（[^）)]*）|\([^)]*\))?\s*[\]】）)]?\s*[：:]\s*",
    re.I)
# 无冒号形式：标签后直接跟空格再接命令（如「运行 python tests」「二级测试 pytest」「RUN python」）
CMD_PREFIX_NOSPACE_RE = re.compile(
    _LINE_PRE + _CMD_LABEL + r"\s*(?:（[^）)]*）|\([^)]*\))?\s*[\]】）)]?\s+(?=[A-Za-z0-9_.\\/])",
    re.I)

# G9：首跑红记录格式（总则 4.8 第 3 步）：首跑红 YYYY-MM-DD｜FAIL n｜<测试标识列表>
# 必须带具体日期（YYYY-MM-DD）、FAIL n（n≥1）、以及至少一个非空测试标识。
FIRST_RED_RE = re.compile(r"首跑红\s+(\d{4}-\d{2}-\d{2})\s*[｜|]\s*FAIL\s+([1-9]\d*)\s*[｜|]\s*(\S+)")

# G9：verified 证据 —— 修 bug 声明 verified 必须附「PASS n 且 FAIL 0」（总则 4.11）。
VERIFIED_EVIDENCE_RE = re.compile(r"verified", re.I)
PASS_FAIL_OK_RE = re.compile(r"PASS\s+[1-9]\d*\b.*\bFAIL\s+0\b|FAIL\s+0\b.*\bPASS\s+[1-9]\d*\b")

# 原子写入的临时文件后缀（同目录 temp + os.replace 原子替换用）
_ATOMIC_SUFFIX = ".wb-tmp"


def atomic_write_text(path, text, fsync_dir=False):
    """同目录临时文件 + flush/fsync + os.replace 原子写文本。

    步骤：
      1. 在同目录创建临时文件（继承目录权限，跨盘问题由同目录规避）
      2. 写入后 flush + fsync（刷到磁盘，防崩溃留下 0 字节/半截）
      3. os.replace 原子替换目标（Windows/POSIX 同目录 rename 原子）
    任何一步失败：删掉临时文件，绝不留半截垃圾；异常向上抛给调用方捕获。
    返回 None。
    """
    target_dir = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(prefix=".wb-", suffix=_ATOMIC_SUFFIX, dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # os.replace 原子替换；目标被锁（Win32 独占）时此处抛 PermissionError，由调用方捕获
        os.replace(tmp_path, path)
        if fsync_dir:
            # 刷目录项，确保 rename 本身落盘（尽力而为，Windows 上目录 fsync 不可靠则跳过）
            try:
                _dfd = os.open(target_dir, os.O_RDONLY)
                try:
                    os.fsync(_dfd)
                finally:
                    os.close(_dfd)
            except OSError:
                pass
    except Exception:
        # 失败：清掉临时文件，不留半截垃圾
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def extract_command(raw):
    """从第 8 段的一行里提取真正的可执行命令。

    识别并剥离各种前缀标签，覆盖卡模板标准写法与各种变体：
      - 「业务测试（二级，必填）：python tests/run_tests.py」
      - 「[二级测试] python tests/run_tests.py」「【运行】python tests/run_tests.py」
      - 「运行：python ...」「二级测试：...」「测试命令：...」「执行 python ...」
      - 「1) 运行：python ...」「RUN: python ...」「说明：运行：python ...」（两级前缀）
    返回干净的「解释器 + 参数」字符串；剥不掉前缀则原样返回（去首尾空白与列表符号）。

    采用循环剥离：一次剥一层，最多剥 5 层，能吃掉「说明：运行：python」这种嵌套前缀。
    """
    s = raw.strip().lstrip("-* `>·").strip()
    for _ in range(5):
        # 1) 冒号形式（「运行：」「[二级测试]：」「业务测试（二级）：」「RUN:」）
        m = CMD_PREFIX_RE.match(s)
        if m:
            s = s[m.end():].strip().lstrip("-* `>·").strip()
            continue
        # 2) 无冒号形式（「运行 python ...」「二级测试 pytest ...」「RUN python」）
        m = CMD_PREFIX_NOSPACE_RE.match(s)
        if m:
            s = s[m.end():].strip().lstrip("-* `>·").strip()
            continue
        break
    # 3) 兜底：若仍以中文/英文标签开头（含方括号/书名号包裹），按常见标签硬切一次
    labels = ("二级测试", "二级闸门", "业务测试", "测试命令", "运行命令", "运行", "执行", "测试",
              "命令", "run", "test", "exec", "execute")
    if s and not re.match(r"^[A-Za-z0-9_.\\/]", s):
        for label in labels:
            for wrapped in (label, "[%s]" % label, "【%s】" % label, "（%s）" % label, "(%s)" % label):
                if s.lower().startswith(wrapped.lower()):
                    rest = s[len(wrapped):].lstrip("：: -（(二级)）").strip()
                    if rest and re.match(r"^[A-Za-z0-9_.\\/]", rest):
                        s = rest
                        break
            else:
                continue
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


def file_fingerprint(path):
    """取文件指纹 (mtime_ns, size, sha256)，用于写回前复核是否被外部改动。

    文件不存在返回 None。读失败（锁/权限）抛 OSError，由调用方捕获。
    """
    if not os.path.isfile(path):
        return None
    st = os.stat(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return (st.st_mtime_ns, st.st_size, h.hexdigest())


def validate_red_date(date_str, now=None):
    """校验首跑红日期语义：格式对 + datetime.fromisoformat 能解析 + 不晚于今天。

    返回 (ok, 错误信息)。ok=True 表示日期合法。
    堵住「2030 年」「13 月 45 日」这类正则能过、语义非法的日期。
    """
    now = now or _dt.datetime.now()
    try:
        d = _dt.datetime.fromisoformat(date_str).date()
    except ValueError:
        return (False, "日期 %s 不是真实日期（如 13 月 45 日）" % date_str)
    if d > now.date():
        return (False, "日期 %s 晚于今天（%s），疑似穿越日期" % (date_str, now.date().isoformat()))
    return (True, "")


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
    body = []
    body.append(f"# 封版归档 {card_id} · {ver}\n\n")
    body.append(f"- 封版时间：{stamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
    body.append(f"- 卡号：{card_id}\n")
    body.append(f"- 版本号：{ver}\n")
    body.append(f"- 归档目的：记录旧版指标，作为回滚对比基准（只读）\n\n")
    body.append("## 旧版指标\n\n")
    if acc_rows:
        body.append("### 验收口径（第 9 段逐条）\n\n")
        for i, cells in enumerate(acc_rows, 1):
            # 第 9 段列序：编号 | 动作 | 期望结果 | 失败表现 | 测试标识
            action = cells[1] if len(cells) > 1 else ""
            expect = cells[2] if len(cells) > 2 else ""
            body.append("- %d. %s → 期望 %s\n" % (i, action, expect))
        body.append("\n")
    else:
        body.append("- 验收口径：见项目卡第 9 段「验收」表\n\n")
    if test_summary:
        body.append(f"### 二级测试（真实回执）\n\n- {test_summary}\n\n")
    else:
        body.append("- 二级测试：未执行（本次封版未跑二级命令）\n\n")
    body.append("> 本文件由 `card_gate.py --seal` 生成。索引同步由封版动作另行更新。\n")
    try:
        atomic_write_text(path, "".join(body))
    except PermissionError as e:
        print("归档：写入失败——文件被独占锁定或无写权限，已放弃且未留半截文件：%s" % e)
        raise
    except OSError as e:
        print("归档：写入失败——%s" % e)
        raise
    return path


def run_secondary_test(cmd, base):
    """实际执行第 8 段的二级测试命令，返回 (exit_code, 输出全文)。

    从输出里抓 PASS/FAIL 数字。命令相对卡所在目录（base）执行。
    先用 extract_command 剥离各种前缀（运行/二级测试/测试命令等），再切分执行。
    """
    import subprocess
    clean = extract_command(cmd)
    # 用 shlex.split 而非 split()：支持带引号的中文空格路径（如 "我的 测试/run_tests.py"）
    try:
        parts = shlex.split(clean, posix=True)
    except ValueError as e:
        return None, "命令引号不闭合，无法解析：%s" % e
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

    返回 (status, message) 元组：
      - ("ok", ...)        成功更新
      - ("not_found", ...) 找不到该卡（或索引.md 不存在、无合法表），未做任何改动
      - ("abnormal", ...)  索引结构异常（多张表 / 同卡号多行），拒绝写入

    安全铁律（红队终审）：
      1. 必须精确定位到「唯一一张」同时含「卡号」「状态」「最后变更日」三个精确
         汉字列名的表；有第二张候选表 → 判结构异常，绝不瞎猜。
      2. 目标卡号在数据行里必须且只能出现一次；出现 0 次 → not_found，出现 ≥2 次
         → 结构异常，拒绝更新。
      3. 只改「状态」「最后变更日」两列，其余列（尤其基线列）一字不动。
    """
    if not os.path.isfile(index_path):
        return ("not_found", "索引.md 不存在")
    # 写回前先记录打开时刻的文件指纹，后面写回前再复核，防 TOCTOU（静默覆盖你手改的内容）
    try:
        fingerprint_before = file_fingerprint(index_path)
    except OSError as e:
        return ("abnormal", "读取索引指纹失败（可能被锁）：%s" % e)
    with open(index_path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    # 1) 先扫描所有「卡号」表头行（首格精确等于「卡号」）。
    #    红队判据：出现 ≥2 个「卡号」表头 = 结构歧义，直接拒绝，不做「挑一张真表」的猜测。
    card_headers = []
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("|"):
            continue
        cells = split_row(ln)
        if not cells:
            continue
        if cells[0].strip() == "卡号":
            card_headers.append(i)

    if len(card_headers) == 0:
        return ("not_found", "索引中无「卡号」表头")
    if len(card_headers) > 1:
        return ("abnormal", "索引存在 %d 张「卡号」表头，结构歧义，拒绝更新" % len(card_headers))

    # 2) 唯一表头：必须同时含精确列名「状态」和「最后变更日」，否则无法安全定位。
    header_idx = card_headers[0]
    cells = split_row(lines[header_idx])
    col_status = col_date = None
    for j, c in enumerate(cells):
        c = c.strip()
        if c == "状态":
            col_status = j
        elif c == "最后变更日":
            col_date = j
    if col_status is None or col_date is None:
        return ("not_found",
                "唯一表头缺「状态」或「最后变更日」列（现有列：%s），无法安全定位，拒绝更新"
                % "、".join(c.strip() for c in cells))

    # 3) 找目标卡号的数据行，必须唯一（≥2 行 = 结构异常）
    target_rows = []
    for i, ln in enumerate(lines):
        if i <= header_idx:
            continue
        if not ln.strip().startswith("|"):
            continue
        cells = split_row(ln)
        if not cells:
            continue
        if cells[0].strip() == card_id:
            target_rows.append((i, cells))

    if len(target_rows) == 0:
        return ("not_found", "索引中无卡号 %s 的数据行" % card_id)
    if len(target_rows) > 1:
        return ("abnormal", "卡号 %s 在索引中出现 %d 行，结构异常，拒绝更新" % (card_id, len(target_rows)))

    i, cells = target_rows[0]
    stamp = _dt.datetime.now().strftime("%Y-%m-%d")
    new_cells = list(cells)
    changed = False
    # 状态列 → 已封版 <version>（只此一列）
    if col_status < len(new_cells) and new_cells[col_status].strip() != ("已封版 " + version):
        new_cells[col_status] = "已封版 " + version
        changed = True
    # 最后变更日列 → 今天（仅当该列值是日期形，避免污染非日期内容）
    if col_date < len(new_cells):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", new_cells[col_date].strip()):
            if new_cells[col_date].strip() != stamp:
                new_cells[col_date] = stamp
                changed = True
    if changed:
        lines[i] = "| " + " | ".join(new_cells) + " |"
        new_text = "\n".join(lines) + "\n"
        # TOCTOU 复核：写回前重新取指纹，若与打开时不一致 → 说明文件被外部改过，拒绝覆盖
        try:
            fingerprint_now = file_fingerprint(index_path)
        except OSError as e:
            return ("abnormal", "写回前复核索引失败（可能被锁）：%s" % e)
        if fingerprint_now != fingerprint_before:
            return ("abnormal",
                    "索引已被外部修改（mtime/size/sha256 与读取时不一致），拒绝覆盖，"
                    "你手改的内容已保住，请先解决冲突再重试")
        try:
            atomic_write_text(index_path, new_text)
        except PermissionError as e:
            return ("abnormal", "索引被独占锁定，无法写入（已放弃，未留半截文件）：%s" % e)
        except OSError as e:
            return ("abnormal", "索引写入失败：%s" % e)
        return ("ok", "已更新 %s 的封版状态与最后变更日" % card_id)
    return ("ok", "卡号 %s 状态已是「已封版 %s」，无需改动" % (card_id, version))


def is_placeholder(v):
    return (not v) or any(p in v for p in PLACEHOLDER)


def pick_test_command(sec8):
    """从第 8 段多行里挑出二级测试命令。

    优先挑「带二级/业务测试标签」的行（如「业务测试（二级）：」「二级测试：」），
    找不到带标签的才回退到任何含可执行特征的行。返回 (干净命令, 是否带二级标签)。

    注意：只有「二级测试 / 业务测试」这类明确指二级测试的标签才算「带标签」；
    「运行 / 执行」是通用词，不算二级测试标签（否则会把「运行：python setup.py」误当测试）。
    """
    candidates = []  # (命令, 是否明确二级标签)
    for ln in sec8:
        s = ln.strip()
        if "待定" in s or "占位" in s:
            continue
        if not TEST_HINT.search(s):
            continue
        # 明确二级标签：含「二级测试」或「业务测试」，或「测试命令」
        is_2nd = bool(re.search(r"二级测试|业务测试|测试命令|二级闸门", s))
        candidates.append((extract_command(s.lstrip("-* ").strip()), is_2nd))
    if not candidates:
        return None, False
    # 优先明确二级标签的行
    for cmd, is_2nd in candidates:
        if is_2nd:
            return cmd, True
    return candidates[0][0], False


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

    # G6：二级测试命令写了没有 + 声明的目标是否真实存在 + 执行结果是否真通过
    sec8 = sec.get(8, (0, []))[1]
    sec10 = sec.get(10, (0, []))[1]
    base = os.path.dirname(os.path.abspath(card))
    # 优先带「二级/业务测试」标签的行，找不到才抓别的（第 8 段多行时不再只抓第一行）
    hit8, hit8_tagged = pick_test_command(sec8)
    g_pn = g_fn = None   # G6 真执行拿到的 PASS/FAIL 数字，归档段复用
    waiver = None
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
            if not os.path.exists(p):
                results.append(("G6", False,
                    "伪造测试：第 8 段写的 %s 不存在（解析为 %s）。新卡无豁免权——"
                    "先建测试文件，或删掉该行改走 4.4 豁免（仅限确无业务测试的项目）" % (tgt, p)))
            else:
                tgt_path = p
                # 铁律（红队三审）：G6 不只查文件存在，还要真正执行二级测试；
                # 退出码非 0 或抓不到 PASS/FAIL 数字 → 判红，不许封版。
                rc, out = run_secondary_test(hit8, base)
                pn, fn = parse_pass_fail(out)
                if rc is None:
                    results.append(("G6", False, "二级测试执行失败：%s" % out[:80]))
                elif rc != 0:
                    results.append(("G6", False,
                        "二级测试退出码 %d（非 0），测试真 FAIL，禁止封版。输出尾部：%s" %
                        (rc, out.strip().splitlines()[-1][:80] if out.strip() else "(空)")))
                elif pn is None or fn is None:
                    results.append(("G6", False,
                        "二级测试退出码 0，但输出未见 PASS/FAIL 数字（无法证明真跑过）。"
                        "须输出 `PASS n`(n≥1) / `FAIL 0`。输出尾部：%s" %
                        (out.strip().splitlines()[-1][:80] if out.strip() else "(空)")))
                elif fn != 0 or pn < 1:
                    results.append(("G6", False,
                        "二级测试数字不合规：PASS %s / FAIL %s，须 PASS n(n≥1) 且 FAIL 0。" % (pn, fn)))
                else:
                    g_pn, g_fn = pn, fn
                    results.append(("G6", True,
                        "命令组含二级测试：%s；目标存在；真执行 PASS %s / FAIL %s（退出码 0）" %
                        (hit8[:40], pn, fn)))
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

                # 虎1.5：日期语义校验 —— 正则能过但日期非法的（2030 年 / 13 月 45 日）
                #         一律判红。用 datetime.fromisoformat 验证真实存在，且不晚于今天。
                now = _dt.datetime.now()
                first_red_bad_date = []
                for d in first_red_ok:
                    m = FIRST_RED_RE.search(d)
                    date_str = m.group(1)
                    ok, err = validate_red_date(date_str, now=now)
                    if not ok:
                        first_red_bad_date.append("「%s」%s" % (date_str, err))
                # 时钟异常告警：台账里声明的最新日期若比系统时间还晚 → 亮灯（不判红）
                clock_warn = []
                for d in decisions:
                    md = re.search(r"(\d{4}-\d{2}-\d{2})", d)
                    if md:
                        try:
                            dd = _dt.datetime.fromisoformat(md.group(1)).date()
                        except ValueError:
                            continue
                        if dd > now.date():
                            clock_warn.append(
                                "台账日期 %s 晚于系统时间 %s（时钟异常或时区跨日）"
                                % (md.group(1), now.date().isoformat()))

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
                if first_red_bad_date:
                    problems.append(
                        "首跑红日期语义非法（不是真实日期，或晚于今天）：" +
                        "；".join(first_red_bad_date))
                if bad_verified:
                    problems.append(
                        "decisions 里有声明 verified 但未附测试输出证据（须 PASS n 且 FAIL 0）的记录：%s" %
                        bad_verified[0][:60])

                if problems:
                    results.append(("G9", False, "；".join(problems)))
                else:
                    detail = "首跑红记录格式合规（%d 条），verified 声明均附测试证据" % len(first_red_ok)
                    if clock_warn:
                        detail += "；⚠ 时钟告警：" + "；".join(clock_warn)
                        # 时钟告警单独打印到 stderr 亮灯，不污染 G9 通过结论
                        print("⚠ 时钟异常告警：" + "；".join(clock_warn), file=sys.stderr)
                    results.append(("G9", True, detail))
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

    # 封版归档：全绿且带 --seal 时，复用 G6 已执行的真实测试结果，写归档摘要 + 同步索引
    if verdict == "通过" and seal_ver is not None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # 1) G6 已真执行二级测试并验证退出码 0 + PASS/FAIL 合规，这里直接复用真实数字
        test_summary = None
        if hit8 and g_pn is not None and g_fn is not None:
            test_summary = "`%s` → 退出码 0，PASS %s / FAIL %s（%s）" % (
                hit8[:48], g_pn, g_fn,
                _dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
        # 2) 回填验收口径（第 9 段真实行）
        acc_rows = table_rows(sec.get(9, (0, []))[1])
        try:
            ap = seal_archive(card_id, seal_ver, base_dir, test_summary=test_summary,
                              acc_rows=acc_rows)
        except (PermissionError, OSError) as e:
            print("封版失败：归档写入异常，已中止（未留半截文件）——%s" % e)
            return 1
        print("归档：已生成 %s" % ap)
        # 3) 同步索引（状态→已封版 vX，最后变更日→今天）
        index_path = os.path.join(base_dir, "索引.md")
        istatus, imsg = update_index(card_id, seal_ver, index_path)
        if istatus == "ok":
            print("索引：%s" % imsg)
        elif istatus == "not_found":
            print("索引：未找到 %s 对应行（%s），跳过" % (card_id, imsg))
        else:  # abnormal：结构异常，判红报错，绝不谎报已更新
            print("索引：结构异常，拒绝更新——%s" % imsg)
            return 1

    return 0 if verdict == "通过" else 1


if __name__ == "__main__":
    sys.exit(main())
