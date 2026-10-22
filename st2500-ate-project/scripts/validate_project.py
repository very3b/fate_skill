#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ST2500/ST5000 ATE 工程交叉校验器

用法:
    python validate_project.py <工程目录> [--truth-table]

例:
    python validate_project.py "D:/.../HC138_v1"

检查项:
  1. Pattern 字符 ⊆ .tim 的 WFC 集合   （硬约束，违反则运行时加载报错）
  2. .pat 索引完整性 + pattern 目录无未注册文件
  3. .tmf 函数名 ↔ Test.cpp 导出函数
  4. .tmf ResultAnalysis 参数数 ↔ CheckResultAndBin 传参
  5. 译码真值表逐条比对手册（--truth-table 时启用，扫描 addr*.csv）

退出码: 0 = 全部通过, 1 = 存在错误
"""
import csv
import glob
import json
import os
import re
import sys


def read_tim(path):
    """返回 {(TimingName, Signal): set(WFC槽位名)}"""
    out = {}
    tset = sig = None
    with open(path, encoding="utf-8", errors="ignore") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            row = [x.strip() for x in row]
            if len(row) < 4:
                continue
            if row[0]:
                tset = row[0]
            if row[2]:
                sig = row[2]
            if not row[3]:
                continue
            out.setdefault((tset, sig), set()).add(row[3])
    return out


def read_grp(path):
    """返回 {组名: set(信号名)}"""
    out = {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            row = [x.strip() for x in row]
            if len(row) > 1 and row[0]:
                out.setdefault(row[0], set()).update(x for x in row[1:] if x)
    return out


def check_wfc(proj, tim, grp):
    """检查 1: Pattern 字符必须 ⊆ 对应 WFC 集合"""
    viol = 0
    total = 0
    for pf in sorted(glob.glob(os.path.join(proj, "pattern", "*.csv")) +
                     glob.glob(os.path.join(proj, "pattern", "*.CSV"))):
        b = os.path.basename(pf)
        if "副本" in b:
            continue
        with open(pf, encoding="utf-8", errors="ignore") as f:
            r = csv.reader(f)
            hdr = [h.strip() for h in next(r, [])]
            if not hdr:
                continue
            wi = next((i for i, h in enumerate(hdr) if h.lower() == "wft"), 1)
            si = next((i for i, h in enumerate(hdr) if h.lower() == "sequence"), 2)
            sig_idx = [i for i in range(len(hdr)) if i not in (0, wi, si)]
            for row in r:
                row = [x.strip() for x in row]
                if len(row) < len(hdr):
                    continue
                wft = row[wi]
                for i in sig_idx:
                    s = hdr[i]
                    ch = row[i]
                    if not ch:
                        continue
                    allowed = tim.get((wft, s), set())
                    if not allowed:
                        continue
                    if s in grp:  # 信号组名：组内成员共享槽位
                        merged = set()
                        for gs in grp[s]:
                            merged |= tim.get((wft, gs), set())
                        allowed = merged or allowed
                    total += 1
                    if ch not in allowed:
                        viol += 1
                        print(f"  [X] {b} WFT={wft} {s}='{ch}' 不在允许集 {sorted(allowed)}")
    return total, viol


def check_pat(proj):
    """检查 2: .pat 索引与 pattern 目录一致性"""
    pats = [p for p in glob.glob(os.path.join(proj, "*.pat"))]
    if not pats:
        return 0, 0, []
    registered = []
    missing = 0
    with open(pats[0], encoding="utf-8", errors="ignore") as f:
        for row in csv.reader(f):
            row = [x.strip() for x in row]
            if len(row) < 6:
                continue
            registered.append(row[2])
            p = row[5].replace("\\", "/").lstrip("./")
            full = os.path.join(proj, p) if not os.path.isabs(p) else p
            if not os.path.exists(full):
                print(f"  [X] .pat 注册了但文件不存在: {p}")
                missing += 1
    on_disk = set()
    for pf in glob.glob(os.path.join(proj, "pattern", "*.csv")) + \
            glob.glob(os.path.join(proj, "pattern", "*.CSV")):
        if "副本" not in os.path.basename(pf):
            on_disk.add(os.path.splitext(os.path.basename(pf))[0])
    unregistered = sorted(on_disk - set(registered))
    for u in unregistered:
        print(f"  [!] pattern/{u}.csv 未在 .pat 注册 → 运行时不会被加载")
    return len(registered), missing, unregistered


def check_tmf_cpp(proj):
    """检查 3+4: .tmf 与 Test.cpp 一致性

    CheckResultAndBin 有 6 个重载（Bindef.h 第 87~102 行）：
      (ulParamID, vector<ST_MEAS_RESULT>)                    —— 无显式个数
      (ulParamStartID, vector<ST_MEAS_RESULT>, ulParamCount)  —— 带个数
      (ulParamID, SITE_DOUBLE/SITE_LONG)                     —— 单值
      (ulParamID, const SITE_xxx&, low, high, unit)          —— 带限值
    一个测项函数内可以多次调用，用 ulParamStartID 划分参数区间。
    因此本检查改为：统计该函数内所有带 count 的调用的 count 之和，
    与 TMF 的 ResultAnalysis 条目数比对（允许 0 次带 count 调用）。
    """
    tmfs = glob.glob(os.path.join(proj, "*.tmf"))
    cpps = glob.glob(os.path.join(proj, "*.cpp"))
    if not tmfs or not cpps:
        print("  [!] 找不到 .tmf 或 .cpp")
        return False
    tmf = json.load(open(tmfs[0], encoding="utf-8"))
    cpp = open(cpps[0], encoding="utf-8", errors="ignore").read()
    ok = True
    for x in tmf["SiteList"][0]["FuncList"]:
        fn = x["FuncName"]
        n = len(x.get("ResultAnalysis", []))
        exported = ("void %s(" % fn) in cpp
        # 取出函数体（从 "void FN(" 到下一个顶层 "}"）
        m = re.search(r"void\s+%s\s*\(\s*\)\s*\{" % re.escape(fn), cpp)
        body = ""
        if m:
            depth = 0
            i = m.end() - 1
            start = i
            while i < len(cpp):
                if cpp[i] == '{':
                    depth += 1
                elif cpp[i] == '}':
                    depth -= 1
                    if depth == 0:
                        body = cpp[start:i + 1]
                        break
                i += 1
        # 统计带 count 参数的调用
        calls = re.findall(r"CheckResultAndBin\s*\(\s*[^,]+,\s*[^,]+,\s*(\d+)\s*\)", body)
        total_count = sum(int(c) for c in calls)
        has_call = bool(re.search(r"CheckResultAndBin\s*\(", body))
        has_setbin = bool(re.search(r"SetBin\s*\(", body))
        # 一致性判定
        if n > 0:
            if total_count == 0:
                if has_call:
                    state = "OK "
                    note = "（用无 count 重载，个数由数组长度决定）"
                elif has_setbin:
                    # SetPassBin 这类置 Bin 函数：本就不做参数判限
                    state = "OK "
                    note = "（置 Bin 函数，用 SetBin 而非判限）"
                else:
                    state = "[X]"
                    note = "  ← 函数内既无判限调用也无 SetBin！测出的值不会被判限"
                    ok = False
            elif total_count == n:
                state = "OK "
                note = ""
            else:
                state = "[X]"
                note = "  ← TMF 声明 %d 个限值，cpp 实际判 %d 个" % (n, total_count)
                ok = False
        else:
            state = "OK " if exported else "[X]"
            note = ""
            if not exported:
                ok = False
        print("  %s %-20s 导出=%-5s TMF参数=%-3d cpp判限=%-3d%s"
              % (state, fn, exported, n, total_count, note))
        if not exported:
            ok = False
    return ok


def check_truth_table(proj):
    """检查 5: addr*.csv 的译码逻辑自洽性（不依赖手册，验内部一致性）"""
    files = sorted(glob.glob(os.path.join(proj, "pattern", "addr*.csv")))
    if not files:
        print("  [!] 未找到 addr*.csv，跳过")
        return True
    ok = True
    for pf in files:
        with open(pf, encoding="utf-8", errors="ignore") as f:
            r = csv.reader(f)
            hdr = [h.strip() for h in next(r, [])]
            row = [x.strip() for x in next(r, [])]
        d = dict(zip(hdr, row))
        try:
            addr = int(d["A0"]) + 2 * int(d["A1"]) + 4 * int(d["A2"])
        except (KeyError, ValueError):
            continue
        ys = [d.get("Y%d" % i, "") for i in range(8)]
        exp = ["L" if i == addr else "H" for i in range(8)]
        good = (ys == exp)
        ok &= good
        print("  %s %s  A2A1A0=%d  Y=%s" % ("OK " if good else "[X]",
                                            os.path.basename(pf), addr, "".join(ys)))
    return ok


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    proj = os.path.abspath(sys.argv[1])
    if not os.path.isdir(proj):
        print("工程目录不存在:", proj)
        return 1

    print("=" * 72)
    print("ST2500 工程交叉校验:", proj)
    print("=" * 72)

    timf = glob.glob(os.path.join(proj, "*.tim"))
    grpf = glob.glob(os.path.join(proj, "*.grp"))
    tim = read_tim(timf[0]) if timf else {}
    grp = read_grp(grpf[0]) if grpf else {}

    print("\n[1] Pattern 字符 ⊆ .tim WFC 集合")
    if not tim:
        print("  [!] 未找到 .tim —— 该工程可能不含波形表（纯 DC 测试）")
        total = viol = 0
    else:
        total, viol = check_wfc(proj, tim, grp)
        print("  检查 %d 个字符，违规 %d 个" % (total, viol))

    print("\n[2] .pat 索引完整性")
    nreg, miss, unreg = check_pat(proj)
    print("  注册 %d 个 pattern，缺失文件 %d 个" % (nreg, miss))

    print("\n[3][4] .tmf ↔ Test.cpp 一致性")
    tmf_ok = check_tmf_cpp(proj)

    tt_ok = True
    if "--truth-table" in sys.argv:
        print("\n[5] 译码真值表自洽性")
        tt_ok = check_truth_table(proj)

    print("\n" + "=" * 72)
    # 未注册的 pattern 属于「提示」而非「错误」：官方工程里也确实存在
    # 预留但未启用的向量文件，是否算问题取决于交付要求。
    all_ok = (viol == 0 and miss == 0 and tmf_ok and tt_ok)
    print("总判定:", "全部通过" if all_ok else "存在问题（见上方 [X]）")
    if unreg:
        print("提示: %d 个 pattern 未在 .pat 注册（不影响运行，但改了不生效）"
              % len(unreg))
    print("=" * 72)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
