#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""巡检.py —— 自动心跳原型（最小可用）

只做三件事，够验证「能红」即可。路由层 / Cron 时间型 属完整版。

命令：
    --check      数轮次：turn_count +1，到 TURN_LIMIT 打印「建议交接」并归零
    --tick       报时间戳：打印上次自检时间与当前时间（只读，无副作用）
    --self-test  负控自检：在临时目录里造「到阈值 / 不到阈值 / 状态缺失」三种情形，
                 断言行为正确；任何一条不对即 exit 1

状态文件：_state/heartbeat.json（可由 --state <路径> 覆盖，供负控隔离）
"""
import datetime
import json
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE = os.path.join(BASE, "_state", "heartbeat.json")
TURN_LIMIT = 15


def load_state(path):
    if not os.path.isfile(path):
        return {"turn_count": 0, "last_selftest_at": "", "last_handoff_at": ""}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(st, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def cmd_check(path=DEFAULT_STATE):
    st = load_state(path)
    st["turn_count"] = int(st.get("turn_count", 0)) + 1
    n = st["turn_count"]
    print("第 %d 轮" % n)
    if n >= TURN_LIMIT:
        print("提示：已到 %d 轮，建议交接换窗口" % TURN_LIMIT)
        st["turn_count"] = 0
    save_state(st, path)
    return 0


def cmd_tick(path=DEFAULT_STATE):
    st = load_state(path)
    last = st.get("last_selftest_at") or "从未"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("心跳 tick｜上次自检：%s｜现在：%s" % (last, now))
    return 0


def _check_once(path, start, expect_remind):
    """单条负控：造状态、跑一次 check、断言打印内容与终值。返回 bool。"""
    save_state({"turn_count": start, "last_selftest_at": "", "last_handoff_at": ""}, path)
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
    for a in args:
        if a.startswith("--state="):
            state = a.split("=", 1)[1]
        elif a.startswith("--"):
            cmd = a
    if cmd is None:
        print("用法：巡检.py --check [--state=路径] | --tick | --self-test")
        return 2
    if cmd == "--check":
        return cmd_check(state)
    if cmd == "--tick":
        return cmd_tick(state)
    if cmd == "--self-test":
        return cmd_selftest()
    print("未知参数：%s" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())
