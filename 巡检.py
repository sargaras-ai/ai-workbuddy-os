#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""巡检.py —— 自动心跳原型（最小可用）

只做三件事，够验证「能红」即可。路由层 / Cron 时间型 属完整版。

命令：
    --check        工作轮：turn_count +1、写 last_check_at，到 TURN_LIMIT 打印「建议交接」并归零
    --check --idle 静默轮（只是聊/别造）：只刷新 last_seen_at，不加 turn_count、不写 last_check_at
    --tick         报时间戳：打印上次自检时间与当前时间（只读，无副作用）
    --self-test    负控自检：在临时目录里造「到阈值 / 不到阈值 / 状态缺失 / 写时间戳 / idle 不计数」
                   五种情形，断言行为正确；任何一条不对即 exit 1

状态文件：_state/heartbeat.json（可由 --state <路径> 覆盖，供负控隔离）

字段说明：
    turn_count      工作轮计数（静默轮不递增）
    last_check_at   上次工作轮打卡时间（静默轮不写）
    last_seen_at    上次任意活跃（工作或静默）时间，供区分「用户没说话」vs「AI 漏跑」
    last_tick_at    上次 tick 打卡时间（只有 --tick 写，与自检解耦，作告警基准）
"""
import datetime
import json
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE = os.path.join(BASE, "_state", "heartbeat.json")
TURN_LIMIT = 15
CHECK_TIMEOUT_MIN = 30


def load_state(path):
    if not os.path.isfile(path):
        return {"turn_count": 0, "last_selftest_at": "", "last_handoff_at": "",
                "last_check_at": "", "last_seen_at": "", "last_tick_at": ""}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_state(st, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def cmd_check(path=DEFAULT_STATE, idle=False):
    st = load_state(path)
    now = _now()
    if idle:
        # 静默轮（只是聊/别造）：只刷新活跃时间，不计数、不写工作打卡
        st["last_seen_at"] = now
        save_state(st, path)
        print("静默轮｜只刷新活跃时间，不计工作轮次")
        return 0
    st["turn_count"] = int(st.get("turn_count", 0)) + 1
    st["last_check_at"] = now
    st["last_seen_at"] = now
    n = st["turn_count"]
    print("第 %d 轮" % n)
    if n >= TURN_LIMIT:
        print("提示：已到 %d 轮，建议交接换窗口" % TURN_LIMIT)
        st["turn_count"] = 0
    save_state(st, path)
    return 0


def _warn_log_path(path):
    return os.path.join(os.path.dirname(path), "tick_warnings.log")


def cmd_tick(path=DEFAULT_STATE):
    st = load_state(path)
    last_tick = st.get("last_tick_at") or "从未"
    last_check = st.get("last_check_at") or "从未"
    last_seen = st.get("last_seen_at") or "从未"
    now = _now()
    print("心跳 tick｜上次 tick：%s｜上次 check：%s｜上次活跃：%s｜现在：%s"
          % (last_tick, last_check, last_seen, now))

    # 告警判定（与自检解耦）：基准是 last_tick_at（只有 --tick 自己写），
    # 不被自检.py 回写刷新，避免「自指悖论」——自检越勤、告警越永不触发。
    # 首跑（从未 tick）或距上次 tick 超时 → 写告警日志（Cron 无聊天窗，控制台看不到）
    warn = False
    if last_tick == "从未":
        warn = True
    else:
        try:
            last_dt = datetime.datetime.strptime(last_tick, "%Y-%m-%d %H:%M:%S")
            if (datetime.datetime.now() - last_dt).total_seconds() / 60.0 > CHECK_TIMEOUT_MIN:
                warn = True
        except ValueError:
            warn = True  # 时间戳格式坏，视为异常
    if warn:
        logp = _warn_log_path(path)
        os.makedirs(os.path.dirname(logp), exist_ok=True)
        with open(logp, "a", encoding="utf-8") as f:
            f.write("%s｜%s\n" % (_now(), "tick 超时" if last_tick != "从未" else "从未 tick"))

    # 最后必须回写 last_tick_at 并保存——本轮 tick 本身就是一次打卡
    st["last_tick_at"] = now
    save_state(st, path)
    return 0


def _check_once(path, start, expect_remind):
    """单条负控：造状态、跑一次 check、断言打印内容与终值。返回 bool。"""
    save_state({"turn_count": start, "last_selftest_at": "", "last_handoff_at": "",
                "last_check_at": "", "last_seen_at": "", "last_tick_at": ""}, path)
    # 捕获 stdout
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_check(path)
    out = buf.getvalue()
    reminded = "建议交接" in out
    end = load_state(path)["turn_count"]
    ok_remind = (reminded == expect_remind)
    # 若提醒了，turn_count 应归零；若没提醒，应停在 start+1
    ok_end = (end == 0) if expect_remind else (end == start + 1)
    return ok_remind and ok_end, out.strip().replace("\n", " / ")


def cmd_selftest():
    tmp = tempfile.mkdtemp(prefix="xunjian-")
    st_path = os.path.join(tmp, "heartbeat.json")
    results = []

    # N1：14 → 15，应提醒并归零
    ok, out = _check_once(st_path, 14, expect_remind=True)
    results.append(("N1 到阈值提醒+归零", ok, out))

    # N2：3 → 4，不应提醒
    ok, out = _check_once(st_path, 3, expect_remind=False)
    results.append(("N2 未到阈值不提醒", ok, out))

    # N3：状态文件缺失，应从 0 重建（不崩）
    if os.path.isfile(st_path):
        os.remove(st_path)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_check(st_path)
    out = buf.getvalue()
    n3_ok = ("第 1 轮" in out) and (load_state(st_path)["turn_count"] == 1)
    results.append(("N3 状态缺失重建", n3_ok, out.strip().replace("\n", " / ")))

    # N4：--check 必须写 last_check_at 时间戳（物理防线的数据来源）
    save_state({"turn_count": 0, "last_selftest_at": "", "last_handoff_at": "",
                "last_check_at": "", "last_seen_at": "", "last_tick_at": ""}, st_path)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_check(st_path)
    n4_ok = bool(load_state(st_path).get("last_check_at"))
    results.append(("N4 check 写时间戳", n4_ok, "last_check_at=%s" % load_state(st_path).get("last_check_at")))

    # N5：--check --idle 只刷新 last_seen_at，不递增 turn_count、不写 last_check_at
    save_state({"turn_count": 5, "last_selftest_at": "", "last_handoff_at": "",
                "last_check_at": "2026-11-17 08:00:00", "last_seen_at": "", "last_tick_at": ""}, st_path)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_check(st_path, idle=True)
    st5 = load_state(st_path)
    n5_ok = (st5["turn_count"] == 5) and (st5["last_check_at"] == "2026-11-17 08:00:00") and bool(st5.get("last_seen_at"))
    results.append(("N5 idle 不计数只刷新", n5_ok,
                    "turn=%d(last_check不变=%s) seen=%s" % (st5["turn_count"], st5["last_check_at"], st5.get("last_seen_at"))))

    # N6：--tick 首跑（从未 tick）应告警落盘，且回写 last_tick_at（打卡）
    save_state({"turn_count": 0, "last_selftest_at": "", "last_handoff_at": "",
                "last_check_at": "", "last_seen_at": "", "last_tick_at": ""}, st_path)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_tick(st_path)
    logp = _warn_log_path(st_path)
    st6 = load_state(st_path)
    n6_ok = (os.path.isfile(logp) and ("从未 tick" in io.open(logp, encoding="utf-8").read())
             and bool(st6.get("last_tick_at")))
    results.append(("N6 tick 首跑告警+打卡", n6_ok,
                    "log=%s last_tick_at=%s" % ("已生成" if os.path.isfile(logp) else "未生成",
                                                st6.get("last_tick_at") or "未写")))

    # N7：紧接着再跑一次 tick，距上次 tick 不足阈值，不应重复告警（日志不追加）
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_tick(st_path)
    n7_log = io.open(logp, encoding="utf-8").read()
    n7_ok = n7_log.count("\n") == 1  # 仍只有首跑那一行
    results.append(("N7 tick 不重复告警", n7_ok,
                    "日志行数=%d（应仍为 1）" % n7_log.count("\n")))

    all_ok = True
    for name, ok, out in results:
        print("%s %s｜%s" % ("PASS" if ok else "FAIL", name, out))
        all_ok = all_ok and ok

    # 清理临时目录
    try:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)
    except OSError:
        pass

    if all_ok:
        print("SELFTEST PASS")
        return 0
    print("SELFTEST FAIL")
    return 1


def main():
    args = sys.argv[1:]
    state = DEFAULT_STATE
    cmd = None
    idle = False
    for a in args:
        if a.startswith("--state="):
            state = a.split("=", 1)[1]
        elif a == "--idle":
            idle = True
        elif a.startswith("--"):
            cmd = a
    if cmd is None:
        print("用法：巡检.py --check [--idle] [--state=路径] | --tick | --self-test")
        return 2
    if cmd == "--check":
        return cmd_check(state, idle=idle)
    if cmd == "--tick":
        return cmd_tick(state)
    if cmd == "--self-test":
        return cmd_selftest()
    print("未知参数：%s" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())
