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

BASE = os.path.dirname(os.path.abspath(__file__))
REL = os.path.join(BASE, "github_release")

# 文档里会被点名的包内文件（都在正本与 clone 后同时存在；开工.py 不在开源包内，故不列）
PACKAGE_FILES = ["总则.md", "暗语表.md", "卡模板.md", "P-00-空白卡.md",
                 "card_gate.py", "开卡.py", "索引.md", "通用坑.md"]

CHECKS = [0]
fails = []


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
    print("\n[心跳机制 %s]" % ("副本" if os.path.isdir(REL) and d == REL else "正本"))
    zongze = read(os.path.join(d, "总则.md")) if os.path.isfile(os.path.join(d, "总则.md")) else ""
    anyu = read(os.path.join(d, "暗语表.md")) if os.path.isfile(os.path.join(d, "暗语表.md")) else ""
    ok("## 七、自动心跳" in zongze, "总则含第七节（自动心跳与巡检）",
       "缺第七节" if "## 七" not in zongze else "")
    ok("自然语言别名" in anyu, "暗语表含自然语言别名表",
       "缺别名表" if "自然语言别名" not in anyu else "")
    ok(os.path.isfile(os.path.join(d, "巡检.py")), "巡检.py 存在",
       "缺巡检.py" if not os.path.isfile(os.path.join(d, "巡检.py")) else "")


# 布局判定：有 github_release/ 就是包目录，否则是克隆下来的仓库
ROLES = [(BASE, "正本", False), (REL, "副本", True)] if os.path.isdir(REL) else [(BASE, "副本(克隆)", True)]

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

print("\n" + "=" * 66)
print("共执行 %d 项检查" % CHECKS[0])
if CHECKS[0] < 12:
    print("FAIL｜检查项过少（%d < 12），脚本自身可能被改坏" % CHECKS[0])
    sys.exit(1)
if fails:
    print("FAIL %d 项：" % len(fails))
    for x in fails:
        print("  - " + x)
    sys.exit(1)
print("PASS 规则自检：%d 项全过" % CHECKS[0])
