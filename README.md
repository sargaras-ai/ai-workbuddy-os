# AI-WorkBuddy-OS · 给 AI 装一套工程纪律

> **一句话**：让 AI 不再靠记忆干活，而是靠**卡片 + 台账 + 闸门**干活。
> 说一句暗语，它建卡、写台账、过闸门；卡不过，它不能声称做完。

[中文](#中文) · [English](#english)

---

## 中文

### 这个仓库解决什么问题

和 AI 长期做项目，你一定遇到过这四件事：

| 症状 | 真实原因 |
|---|---|
| 聊到第 30 轮，它忘了第 3 轮定的技术栈 | 上下文被压缩，没有外部存档 |
| 每个项目都在重新讨论"用什么框架" | 决策没有落成文件，只有对话 |
| 它说"已完成"，你一测就崩 | 「完成」由它自己判定，没有可执行判据 |
| 两个项目的参数互相串味 | 没有隔离机制，全靠模型自觉 |

这套东西的答案很土：**把项目状态从对话里搬进文件，把"完成"的定义交给脚本。**

### 五件套

```
总则.md      怎么记（必记四类 / 不记四类 / 判定线）
暗语表.md    怎么说（22 个口令，每个都有触发条件、生命周期、回执格式）
卡模板.md    记在哪（15 段固定结构，状态行派生不手填）
card_gate.py 谁能说完成（G1–G5 五项机器检查，退出码说话）
开卡.py      怎么开工（一条命令建卡、写台账、追加索引、跑闸门）
```

### 三分钟上手

```bash
git clone <this-repo> ai-workbuddy-os
cd ai-workbuddy-os
```

**① 看一眼"写对了"长什么样**

```bash
python card_gate.py 示例/项目卡-示例.md
# 结论：通过（5/5）
```

**② 开一张自己的卡**

```bash
python 开卡.py P-03-myproject
# 已开卡：P-03-myproject｜根目录：<上级目录>/P-03-myproject
# 台账：_台账.json（4 数组空）｜索引：末行已追加
```

**③ 让 AI 按这套规则干活**

把 `MEMORY.example.md` 的内容抄进你 AI 的长期记忆文件（WorkBuddy / Claude / Cursor 都行），
再补上你自己的偏好（语言、盘符、禁止事项）。**本仓库不提供任何人的私人记忆**，那部分必须你自己写。

之后你对 AI 说：

| 你说 | 它做 |
|---|---|
| `《项目》 P-03-myproject` | 建卡、写台账、追加索引、跑闸门，回一行状态 |
| `落盘` | 把本轮结论写进卡指定段落，回执「路径 + 段落 + 行数」 |
| `只读` | 能跑测试，但一个字都不许写 |
| `交账` | 七段全量对账：目标·约束·承诺·BUG·流程·决策·闸门 |
| `封版` | 打基线，旧值注释保留，不覆盖历史 |

### 闸门：不通过就是不许收工

| 编号 | 检查 | 为什么需要它 |
|---|---|---|
| G1 | 15 段齐全且按序 | 防止 AI 悄悄删掉「非目标」那段 |
| G2 | 每条验收都带**可观察**的失败表现 | 「表现异常」不是判据，「弹窗提示 X」才是 |
| G3 | 参数表无「按需 / 灵活 / 通常 / 一般 / 适当」 | 这五个词是拖延的语法糖 |
| G4 | 待定项四列齐全（字段 / 为什么没定 / 谁定 / 截止日） | 没有截止日的待定＝永远不会定 |
| G5 | 状态行数字 = 台账实际条数 | 防止卡片写着「待办 0」而台账里躺着 3 条 |

退出码：`0` 全通过 / `1` 有不通过项 / `2` 无法检测。

> 局限明写：G2 只能判「非空、非占位、非空话」，判不出失败表现是否**真的**可观察。
> 机器能守住的只有形式，语义那部分仍然要人看。

### 一条设计红线（被真实 bug 教出来的）

> **宁可留空交人工，也不许猜出一个看起来合理的值。**

某次负控测试里，提取逻辑在找不到「价税合计」时，自动退到"页面上唯一的 ￥ 金额"，
结果把**税额**当成了总额，生成了一个看着完全正常的错误文件名。
比"识别失败"危险一百倍——因为没人会去复核它。

所以规则是：缺字段 → 返回空值 + 记 warning → UI 标「需手动填」→ 不生成名字。

### 目录结构

```
ai-workbuddy-os/
├── 总则.md              规则总纲（记忆规则 / 闸门要点 / 存储分层）
├── 暗语表.md            22 个口令 + 优先级 + 生命周期
├── 卡模板.md            15 段结构 + 状态行派生 + 待办/待定分栏
├── P-00-空白卡.md       空卡壳子（开卡时复制它）
├── 索引.md              全局登记表（追加区）
├── 通用坑.md            跨项目坑池（同一坑在 ≥2 个项目复现才收进来）
├── card_gate.py         闸门（仅标准库）
├── 开卡.py              开卡器（仅标准库，全相对路径）
├── MEMORY.example.md    记忆文件模板（请抄成你自己的）
├── LICENSE              MIT（改掉第 3 行的名字即可）
└── 示例/
    ├── 项目卡-示例.md   填满的卡，闸门 5/5 通过
    └── _台账.json       配套台账
```

### 可移植性

仓库内两个脚本都用 `os.path.dirname(os.path.abspath(__file__))` 定位自身，
**不写死任何盘符或绝对路径**。clone 到 `D:\`、`~/code/`、`/opt/` 都能直接跑；
项目目录默认建在仓库的**上级目录**，可用 `--root` 覆盖：

```bash
python 开卡.py P-03-demo --root /path/to/anywhere/P-03-demo
```

依赖：Python 3.6+，**仅标准库，零第三方包**。

### 它不解决什么

- 不替你想需求。定位、目标、非目标，必须你说。
- 不保证 AI 不撒谎。它只保证"撒谎会留下可检查的痕迹"。
- 不适合一次性小脚本。为改三行代码建一张卡，是自找麻烦。

---

## English

### What this is

**An engineering discipline layer for long-running AI projects.**

Not a prompt pack. Not a framework. Five files and two scripts that move project state
*out of the chat window* and *into files with a schema*, then let a script — not the model —
decide whether the work is actually done.

### The four failures it kills

| Symptom | Root cause |
|---|---|
| "We decided this in turn 3" — but it's gone by turn 30 | Context compression, no external state |
| Re-litigating the tech stack on every project | Decisions lived in dialogue, never in files |
| It says "done", your first test says otherwise | The model graded its own homework |
| Project A's port number leaks into project B | No isolation, only good intentions |

### The five pieces

```
总则.md      How to remember   — 4 must-record classes, 4 never-record classes, one decision line
暗语表.md    How to talk       — 22 commands, each with trigger, lifetime, and receipt format
卡模板.md    Where to write    — 15 fixed sections; the status line is derived, never hand-typed
card_gate.py Who may say done  — 5 machine checks, verdict by exit code
开卡.py      How to start      — one command: card, ledger, index, gate
```

### Sixty-second start

```bash
git clone <this-repo> ai-workbuddy-os && cd ai-workbuddy-os
python card_gate.py 示例/项目卡-示例.md     # 结论：通过（5/5） — see a passing card
python 开卡.py P-03-myproject              # create your own
```

Then copy `MEMORY.example.md` into your AI assistant's long-term memory file and fill in
**your own** preferences — language, drives, hard restrictions. This repo deliberately ships
**zero personal memory**; that part is yours to write.

### The gate

| ID | Check | Why |
|---|---|---|
| G1 | All 15 sections present, in order | Stops silent deletion of "non-goals" |
| G2 | Every acceptance row has an **observable** failure mode | "Behaves weirdly" is not a criterion; "popup says X" is |
| G3 | No hedge words in the parameter table | `as needed` / `flexible` / `usually` are procrastination in syntax form |
| G4 | Undecided items carry 4 columns incl. a **decision deadline** | An undated unknown is never decided |
| G5 | Status-line counts == ledger counts | Stops "0 pending" on the card, 3 pending in the ledger |

Exit codes: `0` all pass / `1` some failed / `2` cannot evaluate.

> Stated limitation: G2 verifies *non-empty, non-placeholder, non-vague*. It cannot verify
> that a failure mode is genuinely observable. Machines guard form; humans guard meaning.

### The one red line

> **Leave the field empty and hand it to a human — never guess a plausible value.**

In a negative-control test, the extractor fell back to "the only ￥ amount on the page"
when it could not find the invoice total. It picked up the **tax amount** and produced a
filename that looked perfectly normal and was perfectly wrong. Far more dangerous than a
visible failure, because nobody re-checks a name that looks right.

Rule: missing field → empty value + warning → UI marks "fill manually" → no name generated.

### Portability

Both scripts locate themselves via `os.path.dirname(os.path.abspath(__file__))`.
No hard-coded drives, no absolute paths. Clone anywhere; new projects are created as a
**sibling** of the repo, overridable with `--root`. Requires Python 3.6+ and
**standard library only** — zero third-party dependencies.

### What it does not do

- It will not invent your requirements. Positioning, goals, and non-goals come from you.
- It cannot stop an AI from lying. It does stop lies from being *unverifiable*.
- Not for throwaway scripts. A 15-section card for a 3-line fix is self-harm.

---

## License

MIT —— 随便用，随便改，随便商用，不用署名（保留 LICENSE 里的版权行即可）。

MIT — use it, fork it, sell it. Just keep the copyright notice.

可替换：`LICENSE` 第 3 行的 `Copyright (c) 2026 <YOUR NAME>` 改成你的名字或 GitHub 用户名，其余正文一个字都不用动。
