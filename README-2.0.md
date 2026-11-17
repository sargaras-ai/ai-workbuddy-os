<div align="center">

# AI-WorkBuddy-OS 2.0 · 能力与功能全景清单

**AI-WorkBuddy-OS 2.0 · Capability & Function Overview**

[![Version](https://img.shields.io/badge/version-2.0-blue)](https://github.com/sargaras-ai/ai-workbuddy-os)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.6%2B-yellow)](https://www.python.org/)
[![Stdlib only](https://img.shields.io/badge/deps-zero%20third--party-lightgrey)](#可移植性--portability)
[![Status](https://img.shields.io/badge/status-active-brightgreen)](https://github.com/sargaras-ai/ai-workbuddy-os)

> 一套给 AI 用的「操作系统交通规则」：它不替你写代码，它保证你写代码时——**该问的会问、该拦的会拦、该交接的不会丢、跑没跑到位机器自己会查。**
>
> An "operating-system rulebook" for AI: it doesn't write code for you — it makes sure that when you do, **what should be asked gets asked, what should be blocked gets blocked, what should be handed off never gets lost, and whether it actually ran is checked by a machine, not by memory.**

</div>

---

## 目录 · Table of Contents

- [一、我的权限（你能替我干什么）](#一我的权限你能替我干什么)
- [二、你的底线（哪些坚决不能碰）](#二你的底线哪些坚决不能碰)
- [三、系统能力进化史 1.0 → 2.0](#三系统能力进化史-10--20)
- [快速索引 · Quick Index](#快速索引--quick-index)

---

## 一、我的权限（你能替我干什么）

## What I can do for you

这些是「我」在规则框架下，能**替你自动化**的动作。能替你做 ≠ 能替你拍板——涉及钱、删文件、对外发布、装软件，最后都得你点头。

### 1. 自然语言开卡 · Natural-language card creation

你不用记口令。说「开个项目叫 P-03-记账脚本」，机器照 `暗语表.md` 的别名表**逐字匹配**，自动跑：查重（已存在即中止，绝不覆盖）→ 建目录 → 复制空白卡 → 写台账 → 追加索引 → 跑闸门报 G1–G7。

高频口语词（「好了」「收工」「跑一下」）只做**软提示先问**，绝不自动触发重动作——「好了」可能是「修好了」，也可能是「算了不做了」。

> No commands to memorize. Say "start a project called P-03-bookkeeping" and the machine matches the alias table **verbatim**, then runs: dedup → mkdir → copy the blank card → write the ledger → append the index → run the gate. High-frequency colloquial words ("done", "wrap up", "run it") only **soft-prompt and ask first**, never auto-trigger heavy actions.

### 2. 心跳巡检 · Heartbeat inspection

每次回复前机器自动跑 `巡检.py --check`，往 `_state/heartbeat.json` 打卡；第 15 轮自动提示「该交接换窗口」。靠物理写文件，不靠记性——我忘了跑，超时就被判红。

> Before every reply the machine runs `巡检.py --check`, stamping `_state/heartbeat.json`; at round 15 it prompts "hand off to a new window". It's a physical file write, not memory — if I forget, the timeout goes red.

### 3. 强制闸门拦截 · Enforced gates

- **开卡闸门**（G1–G7）：结构不对、参数表写了「按需/灵活」、测试标识对不上，当场拦。
- **封版闸门**：一级形式卡口 + 二级业务测试，**双过才算过**；`exit 0` 零断言一律判红——**不能失败的闸门等于没有闸门。**

> Open-card gate (G1–G7) and sealing gate (form + business test, both must pass). A zero-assertion `exit 0` goes red — **a gate that can't fail is no gate.**

### 4. 交接不丢 · Lossless handoff

「交接」→ 写 HND 包（现状 + 未闭环 + 下一步）；新窗口 `释放 HND-xxxx` → 复述三样，点头才开工。上下文压缩、换项目、二次封版，强制先交接，不许裸关窗。

> "Hand off" writes an HND package; a new window reads it and restates three things before starting. Compression, project switch, and second seal all force a handoff — no bare window-closing.

### 5. 告警上浮 · Alert surfacing

Cron 每小时跑 `--tick`，超时告警写进日志；下次跑自检时，机器把告警**打印到控制台、读完即清空**——Cron 没聊天窗，但告警不会丢。

> Cron runs `--tick` hourly; stale alerts are logged, then surfaced to the console and cleared on the next self-check — no chat window in Cron, but alerts are never lost.

### 6. 防腐自检 · Anti-rot self-check

改完规则必跑 `自检.py`：查总则和暗语表有没有各说一套、副本有没有被 `cp` 冲掉、点名的文件还在不在。37 项全过才许推。

> After any rule edit, `自检.py` runs 37 checks — consistency, no `cp`-clobbered copy, no dangling file references. Green before push.

---

## 二、你的底线（哪些坚决不能碰）

## What I will never touch

这些是**机器物理拦死**的红线，不是「建议」也不是「尽量」——它们在代码里，不在我的态度里。

### 1. `--force` 拦截 · `--force` is blocked

`开工.py` 的 `--force` 会把卡式台账改写成旧 schema，`card_gate` 的 G5 当场崩。禁用，机器拦、规则也写死。

> `--force` rewrites the card ledger into the legacy schema and breaks G5 immediately. Blocked by machine and by rule.

### 2. 红蓝审查机制 · Red-team review

我不给自己放行。外部红队交叉审计挑出的致命伤，一条条修复并配负控（负控 = 验证「闸门真的能拦住」的测试）。自指悖论、高频词误触发、删文件绕过——都是被红队逼出来、再用负控钉死的。

> I don't rubber-stamp myself. Fatal flaws found by external red-team audit are fixed one by one and pinned with negative controls — tests that prove the gate actually blocks.

### 3. 只读豁免（边界写死）· Read-only exemption (explicit boundary)

`只读` 态下我能跑不能写，**唯一例外**是心跳引擎自己的元数据（`heartbeat.json`、`tick_warnings.log`）——那是我自检的零件，不是你的业务文件。除此之外写任何业务文件，一律违约。

> Under `只读` I may run but not write; the **only** exception is the heartbeat engine's own metadata — my own parts, not your business files. Anything else is a breach.

### 4. 问 ≠ 做 · Ask ≠ Act

没听到动作词（做/生成/写/帮我/改/搬），就只给答案不动手。附件不等于指令；两段式指令只做第一段；缺信息先问，不假定。

> No action verb → answer only, no action. An attachment is not an order; a two-part order runs only the first part; missing info → ask, don't assume.

### 5. 删除铁律 · The deletion iron rule

未经逐项确认，绝不「删进回收站」——回收站共享，我一删你一清空就成了批量删除。先列清单（路径 + 体积 + 为什么该删），等你点名才动，只删你点的那一个。

> Never delete into a shared recycle bin without per-item confirmation. List first (path + size + reason), wait for your call, delete only the one you named.

### 6. 事实纪律 · Fact discipline

每条数字带来源和日期；拿不到来源写「待验证」，不打包票。价格当次现搜，多平台并列，不拿旧价糊弄。

> Every number carries a source and date; no source → "unverified", never a guarantee. Prices are searched fresh, multi-platform, never a stale reference.

---

## 三、系统能力进化史：1.0 → 2.0

## Evolution: 1.0 → 2.0

### 引擎 1.0：纯规则 · v1.0 — rules only

> 一份「总则 + 暗语表」，靠**人脑**记住和遵守。三条痛点：**人脑负荷过载、无法自动巡检、暗语太多记不住。** 说白了——「写在纸上的规矩」，守不守得住，看 AI 心情。

> A rulebook remembered and obeyed by *a human brain*. Three pain points: cognitive overload, no automatic inspection, too many commands to memorize. In short: rules on paper, honored only if the AI feels like it.

### 引擎 2.0：心跳闭环 · v2.0 — heartbeat closed loop

> 把「自觉」换成「机器自查 + 人只管决策」。

> Replace "self-discipline" with "machine self-checks + human only decides".

| 维度 · Dimension | 1.0 纯规则 | 2.0 心跳闭环 |
|---|---|---|
| 谁执行规则 · Who enforces | 靠 AI 记性 | 机器逐字匹配 API，不猜 |
| 偷懒查得出来吗 · Detectable slacking | 查不出 | 心跳超时判红 |
| 规则腐化谁发现 · Who spots rule rot | 靠人偶然撞见 | 自检 37 项，绿了才许推 |
| 告警去哪 · Where alerts go | 无 | 落盘 + 下次自检上浮，不丢 |
| 闸门能拦住吗 · Gates that block | 写个 `exit 0` 就过 | 零断言判红，负控证明真能拦 |

### 你获得了什么 · What you gain

**一句话：从「祈祷 AI 别忘」到「忘了一定被抓」。**

- **省心**：不用当监工，机器替你盯着。
- **省事**：自然语言开卡，口令不用背。
- **省命（少返工）**：规则腐化、副本漂移、测试造假这些「安静地出错」的问题，改完当场红。
- **省责**：该问的会问、该拦的会拦、该交接的不会丢——你不会因 AI「自作主张」背锅。

**代价也很诚实**：多一层 `_state` 状态文件、多跑几次 `--check`/`--tick`，换来「我能证明跑到位」，而不是「我保证跑到位」。**保证会撒谎，退出码不会。**

> **One line: from "pray the AI remembers" to "if it forgets, it gets caught."** You stop being a supervisor, stop memorizing commands, stop discovering rot by accident, and stop taking blame for an AI going rogue. The honest cost: a `_state` file and a few extra `--check`/`--tick` runs, buying "I can prove it ran" instead of "I promise it ran". **Promises lie; exit codes don't.**

---

## 快速索引 · Quick Index

| 你要找的 · You're looking for | 去哪看 · Where |
|---|---|
| 总规则 · Core rules | `总则.md` |
| 口令 + 自然语言别名 · Commands + aliases | `暗语表.md` |
| 心跳巡检 · Heartbeat | `巡检.py`（`--check` / `--tick` / `--self-test`） |
| 防腐自检 · Anti-rot | `自检.py` |
| 开卡闸门 · Open-card gate | `card_gate.py` + `开卡.py` |
| 交接 · Handoff | `~/.workbuddy/skills/handoff/SKILL.md` |

---

<div align="center">

**MIT License** · Copyright (c) 2026 [sargaras](https://github.com/sargaras-ai)

</div>
