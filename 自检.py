# -*- coding: utf-8 -*-
"""规则自检（防腐剂）：查 总则.md / 暗语表.md 是否走样，副本是否被 cp 冲掉。

用法（在包目录或 clone 下来的仓库里都能跑，脚本靠 __file__ 找自己）：
    python 自检.py                 # 查本目录 + github_release/ 下的两个文件
    python 自检.py <文件> [...]    # 负控用：只查指定文件

退出码：0 全过 / 1 有不通过项

布局自适应：
    包目录（正本 + github_release/ 副本）  → 两侧都查，且查「副本未被正本原样覆盖」
    克隆的仓库（只有一份）                  → 只按副本口径查（不得出现盘符路径）

它拦得住什么（每条都有对应负控）：
  1 生命周期漏词      第一节新增暗语，第三节没登记
  2 交集排序退回      只读 被排到 先别动/待命 前面（越权风险）
  3 旧口径残留        G1–G6、G2/G4 这些加闸门后没跟上的数字
  4 只读禁令位置      回落到「触发条件」而非执行首条硬规则
  5 路由不一致        总则兜底序 ≠ 暗语表交集序（两份规则各说一套）
  6 副本被 cp 覆盖    正本与副本逐字节相同 —— 适配版被冲掉，最难自己发现的一种
  7 副本盘符泄漏      副本里出现 C:\\ D:\\ 之类本机路径
  8 引用悬空          文档里点名的包内文件不存在（HND 模板那种空引用）
  9 心跳机制齐备      总则第七节 / 暗语表别名表 / 巡检.py 三者都在（重构后防漏）

局限（明写）：只认字面，判不出语义；文案换了说法它看不懂，只能拦结构性问题。
"""
import io
import os
import re
import sys
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
REL = os.path.join(BASE, "github_release")

# 文档里会被点名的包内文件（都在正本与 clone 后同时存在；开工.py 不在开源包内，故不列）
PACKAGE_FILES = ["总则.md", "暗语表.md", "卡模板.md", "P-00-空白卡.md",
                 "card_gate.py", "开卡.py", "索引.md", "通用坑.md"]

CHECKS = [0]
fails = []

# 心跳超时阈值（分钟）：last_check_at 距现在超过它，自检判红
CHECK_TIMEOUT_MIN = 30


def ok(cond, label, detail=""):
    CHECKS[0] += 1
    print("  %s %s%s" % ("✓" if cond else "×", label, ("｜" + detail) if detail else ""))
    if not cond:
        fails.append(label + ("：" + detail if detail else ""))
    return cond


def read(path):
    return io.open(path, encoding="utf-8").read().replace("\r\n", "\n")


def order_tokens(text):
    return [t.split("/")[0].strip() for t in text.split(">")]


def check_anyu(path, s, role, is_copy):
    print("\n[暗语表 %s]" % role)

    i1, i2, i3 = s.find("## 一、"), s.find("## 二、"), s.find("## 三、")
    if min(i1, i2, i3) < 0:
        ok(False, "章节完整（一/二/三）", "缺章节")
        return None
    sec1, sec2, sec3 = s[i1:i2], s[i2:i3], s[i3:]

    # 1 第一节的词必须在第三节登记
    words = []
    for ln in sec1.split("\n"):
        if ln.startswith("| `"):
            words += [w.strip() for w in re.findall(r"`([^`]+)`", ln.split("|")[1])]
    words = [w for w in words if w]
    missing = [w for w in words if ("`%s`" % w) not in sec3]
    ok(len(words) >= 30, "第一节词数可提取", "%d 个" % len(words))
    ok(not missing, "生命周期全覆盖（%d 词）" % len(words),
       ("漏：" + "、".join(missing)) if missing else "")

    # 2 交集排序：先别动/待命 必须在 只读 之前
    m = re.search(r"`只是聊/别造 > ([^`]+)`", sec2)
    order = m.group(1) if m else ""
    pos_wait, pos_ro = order.find("先别动"), order.find("只读")
    ok(bool(order) and pos_wait >= 0 and pos_ro > pos_wait, "交集排序（保守优先）", order or "未找到")

    # 3 旧口径残留
    ok(not re.findall(r"G1[–-]G6", s), "无 G1–G6 旧口径")
    ok(not re.findall(r"G2/G4(?![/]G6)", s), "无 G2/G4 旧口径")

    # 4 封版行：只读禁令必须在执行动作里
    row = [ln for ln in s.split("\n") if ln.startswith("| `封版`")]
    if not row:
        ok(False, "封版行存在")
    else:
        cells = row[0].split("|")
        trig, act = cells[3], cells[5]
        ok("只读" not in trig and "硬规则" in act and "先解除只读" in act,
           "只读禁令在执行动作首条", "触发条件=%s" % trig.strip())

    # 副本必须干净（正本本来就是本机路径，不查也不算项）
    if is_copy:
        hits = re.findall(r"[A-Za-z]:[\\/]", s)
        ok(not hits, "副本无盘符路径",
           "" if not hits else "%d 处，首处 %.30s" % (len(hits), hits[0]))

    return order_tokens(order) if order else None


def check_zongze(s, role, anyu_order, is_copy):
    print("\n[总则 %s]" % role)

    m = re.search(r"兜底序\s*([^（(\n]+)", s)
    zs = order_tokens(m.group(1).replace(" ", "")) if m else []
    while zs and zs[0] == "只是聊":      # 总则多带最左一档，对齐后再比
        zs.pop(0)
    same = bool(anyu_order) and zs == anyu_order
    ok(same, "兜底序与暗语表一致（路由不打架）",
       "总则=%s / 暗语表=%s" % (">".join(zs) or "未找到", ">".join(anyu_order or []) or "未找到"))

    ok(not re.findall(r"G1[–-]G6", s), "无 G1–G6 旧口径")
    ok(not re.findall(r"G2/G4(?![/]G6)", s), "无 G2/G4 旧口径")
    ok("G7" in s, "含 G7（封版映射已机器化）")
    if is_copy:
        hits = re.findall(r"[A-Za-z]:[\\/]", s)
        ok(not hits, "副本无盘符路径",
           "" if not hits else "%d 处，首处 %.30s" % (len(hits), hits[0]))


# 9 心跳机制齐备（重构后防漏）：三样必须都在 —— 总则第七节 / 暗语表别名表 / 巡检.py
def check_heartbeat(d):
    print("\n[心跳机制 %s]" % ("副本" if is_package_layout() and d == REL else ("正本" if is_master_dir(d) else "副本(克隆)")))
    zongze = read(os.path.join(d, "总则.md")) if os.path.isfile(os.path.join(d, "总则.md")) else ""
    anyu = read(os.path.join(d, "暗语表.md")) if os.path.isfile(os.path.join(d, "暗语表.md")) else ""
    ok("## 七、自动心跳" in zongze, "总则含第七节（自动心跳与巡检）",
       "缺第七节" if "## 七" not in zongze else "")
    ok("自然语言别名" in anyu, "暗语表含自然语言别名表",
       "缺别名表" if "自然语言别名" not in anyu else "")
    ok("软提示" in anyu, "别名表含词频分级（软提示/直连，P0-8）",
       "别名表退化为无分级的旧版，高频词会误触发" if "软提示" not in anyu else "")
    ok(os.path.isfile(os.path.join(d, "巡检.py")), "巡检.py 存在",
       "缺巡检.py" if not os.path.isfile(os.path.join(d, "巡检.py")) else "")

    # 超时红（P0-3 两态 + P0-12 缺失不静默跳过）
    state_path = os.path.join(d, "_state", "heartbeat.json")
    is_master = is_master_dir(d)  # 正本（本机真实状态）才做心跳判红；副本/clone 无真实状态，只查结构
    if not os.path.isfile(state_path):
        # P0-12：状态文件缺失不是「可跳过」，而是「防线被绕过」的异常信号 → 判黄（提示但不阻断）
        if is_master:
            ok(False, "心跳状态文件存在（_state/heartbeat.json）",
               "缺失——若被删除，超时红防线会静默失效")
        # 副本/clone 本就没有状态文件，不判红
        return

    try:
        import json as _json
        import datetime as _dt
        st = _json.loads(read(state_path))
    except Exception as e:
        if is_master:
            ok(False, "心跳状态文件可读", "读 %s 失败：%s" % (state_path, e))
        return

    # 两态判断：区分「用户没说话」vs「AI 漏跑」
    #   last_seen_at = 最近一次任意活跃（工作或静默），说明「AI 被唤醒过」
    #   last_check_at = 最近一次工作轮打卡，说明「AI 在活跃时跑了 --check」
    #   只有「AI 被唤醒过、却长时间没跑工作 check」才是漏跑；「用户根本没说话」不判红。
    seen = st.get("last_seen_at", "")
    lc = st.get("last_check_at", "")

    def parse_min_ago(ts):
        try:
            return (_dt.datetime.now() - _dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60.0
        except (ValueError, TypeError):
            return None

    # 从未有任何活跃记录 → 引擎刚装好 / 状态被清，提示但不算「AI 失职」
    if not seen:
        if is_master:
            ok(False, "心跳有活跃记录（last_seen_at 非空）",
               "从未记录活跃——首次部署或状态被清，先跑一次 --check 建立基线")
        return

    seen_min = parse_min_ago(seen)
    # 用户最近还在说话（活跃时间很近）但工作 check 却很久没更新 → 这才是「AI 漏跑」
    if lc:
        lc_min = parse_min_ago(lc)
        if lc_min is None:
            if is_master:
                ok(False, "last_check_at 可解析", "格式错：%s" % lc)
        elif lc_min > CHECK_TIMEOUT_MIN and seen_min is not None and seen_min <= CHECK_TIMEOUT_MIN:
            # 活跃很近 + 工作打卡超时 = AI 漏跑，判红
            if is_master:
                ok(False, "工作轮已打卡（last_check_at 未超时）",
                   "活跃于 %.0f 分钟前，但已 %.0f 分钟未跑工作 --check（漏跑）" % (seen_min, lc_min))
        else:
            ok(True, "工作打卡未漏（静默期不误报）",
               "活跃 %.0f 分钟前 / 打卡 %.0f 分钟前" % (seen_min or 0, lc_min or 0))
    else:
        # 有活跃记录但从未工作打卡 → 可能是纯闲聊期，不判红（这正是 P0-3 要避免的误报）
        if is_master:
            ok(True, "静默期不误报（无工作打卡不判红）",
               "有活跃记录但无工作打卡，视为纯闲聊期，不判红")


# 告警上浮：tick 告警日志有内容就打印到控制台，读完即清空（Cron 无聊天窗，靠下次自检带出来）
def check_warn_log(d):
    logp = os.path.join(d, "_state", "tick_warnings.log")
    if not os.path.isfile(logp):
        return
    try:
        content = read(logp)
    except Exception:
        return
    if content.strip():
        print("\n[tick 告警上浮] 发现待处理告警：")
        for ln in content.strip().split("\n"):
            print("  ! " + ln)
        # 读完即清空，避免下次重复上报
        try:
            os.remove(logp)
        except OSError:
            pass


# 10 承诺对账（B5 根治）：文档里写死「自检 N 项」的数字承诺，必须等于本布局实测项数。
#    审计结论：B1/B3 全因「README 写 13 项、实测 18 项」这种承诺漂移没人管。本函数扫描
#    README*.md 里所有「自检」语境下的写死数字，与实测 expect_count 做减法，不一致直接报红。
#    B3 已把写死数字改成「以实测为准」，此闸门防的是「未来又写死且写错」。
#    注意：本函数是「元检查」，不调 ok() 计数（否则会污染「共执行 N 项」），只往 fails 追加。
def check_promise_ledger(d, expect_count):
    print("\n[承诺对账 %s]" % ("正本" if is_master_dir(d) else "副本(克隆)"))
    readmes = [os.path.join(d, "README.md"), os.path.join(d, "README-2.0.md")]
    readmes = [p for p in readmes if os.path.isfile(p)]
    if not readmes:
        print("  （无 README，跳过承诺对账）")
        return
    found_any = False
    for rp in readmes:
        txt = read(rp)
        for m in re.finditer(r"自检[^\n]{0,40}?(\d+)\s*项", txt):
            num = int(m.group(1))
            found_any = True
            if num != expect_count:
                fails.append("承诺对账（%s 写「自检 %s 项」）：实测本布局 %d 项 → 漂移"
                             % (os.path.basename(rp), num, expect_count))
        for m in re.finditer(r"PASS\s*规则自检[^\n]{0,30}?(\d+)\s*项", txt):
            num = int(m.group(1))
            found_any = True
            if num != expect_count:
                fails.append("承诺对账（%s 写「PASS ... %s 项」）：实测本布局 %d 项 → 漂移"
                             % (os.path.basename(rp), num, expect_count))
    if found_any:
        print("  扫到写死项数承诺，已与实测 %d 项比对" % expect_count)
    else:
        print("  未扫到写死自检项数（B3 达标，以实测为准，不会漂移）")


# 布局判定：有 github_release/ 就是包目录（正本 + 副本），否则是克隆下来的仓库（只有一份）
# B2 根因修复：身份判定统一成下面两个函数，三处（心跳标签 / is_master / ROLES）都调它，
#             不再各自用「d==BASE」「d==REL」「有没有子目录」三种口径互相打架。
def is_package_layout():
    """是否有 github_release/ 子目录 —— 这是「作者包目录」最硬的一条硬盘事实。"""
    return os.path.isdir(REL)


def is_master_dir(d):
    """d 是否为「正本」（有真实心跳状态、要判超时红）的那一侧。
    clone 布局下 d 就是 BASE，但因为没有 github_release/，它只是「唯一一份」，
    不是「正本」——必须用 is_package_layout() 区分，否则 clone 会被误判成正本、
    要求一个 clone 里永远不存在的 _state/heartbeat.json（B2 的 18 项 FAIL 1 就出在这）。
    """
    return is_package_layout() and d == BASE


# 布局判定：有 github_release/ 就是包目录，否则是克隆下来的仓库
ROLES = [(BASE, "正本", False), (REL, "副本", True)] if is_package_layout() else [(BASE, "副本(克隆)", True)]

targets = sys.argv[1:]
if targets:
    for p in targets:
        print("=" * 66)
        if not os.path.isfile(p):
            print("[缺失] %s" % p)
            fails.append("文件缺失：" + p)
            continue
        s = read(p)
        copy = os.path.basename(os.path.dirname(p)) == "github_release"
        if "暗语表" in os.path.basename(p):
            check_anyu(p, s, "副本" if copy else "正本", copy)
        else:
            check_zongze(s, "副本" if copy else "正本", None, copy)
else:
    for d, role, is_copy in ROLES:
        print("=" * 66)
        print("布局：%s（%s）" % (d, role))
        missing_doc = [f for f in ("暗语表.md", "总则.md") if not os.path.isfile(os.path.join(d, f))]
        if missing_doc:
            ok(False, "两侧文档齐全", "缺：" + "、".join(missing_doc))
            continue
        order = check_anyu(os.path.join(d, "暗语表.md"), read(os.path.join(d, "暗语表.md")), role, is_copy)
        check_zongze(read(os.path.join(d, "总则.md")), role, order, is_copy)
        check_heartbeat(d)
        if d == BASE:
            check_warn_log(d)

        # 8 文档点名的包内文件必须真实存在（抓「HND 模板」那种悬空引用）
        docs = read(os.path.join(d, "总则.md")) + read(os.path.join(d, "暗语表.md"))
        gone = [f for f in PACKAGE_FILES
                if ("`%s`" % f) in docs and not os.path.isfile(os.path.join(d, f))]
        ok(not gone, "引用无悬空（%d 个点名文件都在）" % len(PACKAGE_FILES),
           ("缺：" + "、".join(gone)) if gone else "")

        # 6 副本被 cp 原样覆盖（正本与副本逐字节相同 = 适配丢失）
        if is_copy and os.path.isdir(REL):
            for f in ("总则.md", "暗语表.md"):
                twin = os.path.join(BASE, f)
                if os.path.isfile(twin) and os.path.isfile(os.path.join(d, f)):
                    same_bytes = io.open(twin, "rb").read() == io.open(os.path.join(d, f), "rb").read()
                    ok(not same_bytes, "副本 %s 未被正本原样覆盖" % f,
                       "与正本逐字节相同 → 疑似 cp 覆盖，适配丢失" if same_bytes else "")

        # 6b 副本章节骨架一致性（P1-13）：副本多一节/少一节/标题对不上 → 红
        #     只比「章节标题序列」，不比正文——正文本就允许适配差异（如副本多一句 TURN_LIMIT 说明）
        if is_copy and os.path.isdir(REL):
            for f in ("总则.md", "暗语表.md"):
                twin = os.path.join(BASE, f)
                copy_p = os.path.join(d, f)
                if not (os.path.isfile(twin) and os.path.isfile(copy_p)):
                    continue
                def _titles(path):
                    return re.findall(r"^#{2,3}\s+.+", read(path), re.M)
                t_main, t_copy = _titles(twin), _titles(copy_p)
                ok(t_main == t_copy, "副本 %s 章节骨架与正本一致" % f,
                   "正本 %d 个标题 / 副本 %d 个（漂移）" % (len(t_main), len(t_copy)) if t_main != t_copy else "")

print("\n" + "=" * 66)
print("共执行 %d 项检查" % CHECKS[0])
if CHECKS[0] < 12:
    print("FAIL｜检查项过少（%d < 12），脚本自身可能被改坏" % CHECKS[0])
    sys.exit(1)

# 承诺对账（B5）：无参数全量跑完后，用定格后的实测项数扫 README 写死数字，漂移则报红
if not targets:
    check_promise_ledger(BASE, CHECKS[0])


# 全量跑完，回写自检时间戳到正本心跳状态（--tick 与下次超时红的基准）
if not targets and os.path.isdir(os.path.join(BASE, "_state")):
    import json as _json
    state_path = os.path.join(BASE, "_state", "heartbeat.json")
    st = {}
    if os.path.isfile(state_path):
        try:
            st = _json.loads(read(state_path))
        except Exception:
            st = {}
    st["last_selftest_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with io.open(state_path, "w", encoding="utf-8") as f:
        _json.dump(st, f, ensure_ascii=False, indent=2)

if fails:
    print("FAIL %d 项：" % len(fails))
    for x in fails:
        print("  - " + x)
    sys.exit(1)
print("PASS 规则自检：%d 项全过" % CHECKS[0])
