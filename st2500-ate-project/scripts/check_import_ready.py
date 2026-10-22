#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ST-IDE 导入预检器 —— 在 Import 对话框打开前就发现问题

用法:
    python check_import_ready.py <工程目录> [--ws <workspace路径>]

原理（来自 com.urt.mini.application 插件反编译源码 WizardJobImportPage.java）:

  灰色 (hasConflicts / isInvalid) 的两个触发条件：
    1. isProjectInWorkspacePath(name): workspace/<name> 目录存在
    2. isProjectInWorkspace(name):     该名字已在 workspace 注册表里
    3. 收集阶段: .job 文件名(去扩展名) 必须等于其所在目录名

  hasConflicts = (isProjectInWorkspacePath && !isFromWorkspace) || isProjectInWorkspace

本脚本用与 IDE 完全相同的规则做预检，避免用户在 GUI 里反复试。
"""
import glob
import json
import os
import sys

DEFAULT_WS = r"D:\MINI-ATE\workspace"


def ide_style_path(p):
    """模拟 Java File.getPath() / IPath.toFile() 的行为"""
    return os.path.abspath(p)


def collect_jobs(root, ws_path):
    """复现 collectProjectFilesFromDirectory"""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".metadata"]
        for fn in filenames:
            if not fn.endswith(".job"):
                continue
            job_name = fn[: fn.rfind(".")]
            parent_name = os.path.basename(dirpath)
            # checkJobProjectFormat: 父目录不能就是 workspace 本身
            if ide_style_path(dirpath) == ws_path:
                continue
            if job_name.lower() != parent_name.lower():
                found.append((os.path.join(dirpath, fn), job_name, parent_name, "invalid"))
                continue
            found.append((os.path.join(dirpath, fn), job_name, parent_name, "ok"))
    return found


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    proj = os.path.abspath(sys.argv[1])
    ws = DEFAULT_WS
    if "--ws" in sys.argv:
        ws = sys.argv[sys.argv.index("--ws") + 1]
    ws = ide_style_path(ws)

    if not os.path.isdir(proj):
        print("工程目录不存在:", proj)
        return 1

    reg_root = os.path.join(ws, ".metadata", ".plugins",
                            "org.eclipse.core.resources", ".projects")
    registered = {os.path.basename(p) for p in glob.glob(os.path.join(reg_root, "*"))}

    print("=" * 74)
    print("ST-IDE 导入预检")
    print("=" * 74)
    print("工程目录 :", proj)
    print("workspace:", ws)
    print("已注册工程:", ", ".join(sorted(registered)) if registered else "(无)")
    print()

    # 检查 .job 文件名与目录名是否一致
    jobs = collect_jobs(proj, ws)
    if not jobs:
        print("[X] 该目录下没找到任何 .job 文件")
        print("    IDE 的导入向导靠 .job 文件发现工程，找不到就不会列出。")
        return 1

    all_ok = True
    for job_file, job_name, parent_name, state in jobs:
        print("  .job:", os.path.relpath(job_file, proj))

        # 条件 A：.job 文件名必须等于所在目录名
        if state == "invalid":
            print("    [X] .job 文件名 '%s' 与所在目录名 '%s' 不一致" % (job_name, parent_name))
            print("        IDE 要求两者相同（大小写不敏感），否则该工程进不了列表。")
            all_ok = False
            continue
        print("    OK  文件名与目录名一致")

        # 条件 B：workspace 下不能有同名目录
        ws_dir = os.path.join(ws, job_name)
        if os.path.exists(ws_dir):
            print("    [X] workspace 下已存在同名目录 -> 导入列表里会显示为灰色不可勾选")
            print("        %s" % ws_dir)
            print("        解决：① 改名导入（如 %s_V2）② 或先移走该目录" % job_name)
            all_ok = False
        else:
            print("    OK  workspace 下无同名目录")

        # 条件 C：不能已在 IDE 注册表里
        if job_name in registered:
            print("    [X] '%s' 已在 IDE 注册表中 -> 同样显示为灰色" % job_name)
            print("        注册表: %s" % os.path.join(reg_root, job_name))
            all_ok = False
        else:
            print("    OK  未在 IDE 注册表中")

        # 附加：.job 内部路径字段建议用反斜杠
        try:
            d = json.load(open(job_file, encoding="utf-8"))
            jd = d.get("jobDir", "")
            ah = d.get("AteHomePath", "")
            if "//" in str(jd):
                print("    [!] jobDir 用了双斜杠 '%s'" % jd)
                print("        IDE 生成的格式是反斜杠：D:\\MINI-ATE\\workspace\\<name>")
            if "//" in str(ah):
                print("    [!] AteHomePath 用了双斜杠 '%s'" % ah)
                print("        IDE 生成的格式是反斜杠：d:\\MINI-ATE")
        except Exception as e:
            print("    [!] .job 解析失败:", e)
        print()

    print("=" * 74)
    if all_ok:
        print("预检通过：导入时应可正常勾选。")
    else:
        print("预检发现问题：按上面提示处理后再导入。")
    print("=" * 74)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
