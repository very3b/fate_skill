---
name: st2500-ate-project
description: 为加速科技 ST2500/ST5000 ATE 测试机新建、调试或修复完整测试工程（.job/.sig/.grp/.res/.tim/.pat/.tmf + Test.cpp + Makefile + pattern CSV）。当用户提到 ST2500、ST5000、加速科技、MINI-ATE、ST-IDE、ATE 案例、译码器/计数器/MCU 芯片测试工程、导入变灰、Test.dll 编译失败、pattern 时序设计、测试方案限值提取时使用。
agent_created: true
---

# ST2500/ST5000 ATE 测试工程构建与调试

本 skill 沉淀了加速科技 ST2500 ATE 测试机的完整工程构建方法。所有结论均来自
本机 `D:\MINI-ATE` 的官方 API 手册（`doc\ST2500&&ST5000_API_20211115_V2.4.chm`）、
教学课件、以及 `com.urt.mini.application` 插件的**反编译源码**（CFR 反编译
`plugins\com.urt.mini.application_*.jar` 得到 `WizardJobImportPage.java` 等），
不是凭印象推断。

## 工程文件全景

一个 ATE 测试工程 = 8 类文件，缺一不可：

| 文件 | 作用 | 最易出错处 |
|------|------|-----------|
| `X.job` | 工程入口（JSON），指向其余所有文件 | `jobDir`/`jobFilePath` 的**反斜杠**写法 |
| `X.sig` | 信号→通道映射（`SigName,AFEType,ChType,Site0_CH`） | `Site0_CH` 格式 `板卡:资源:通道` |
| `X.grp` | 信号分组（`GrpName,SigName` 逗号分隔） | 分组决定 `pinlevel` 能否单独给某脚施压 |
| `X.res` | 机台资源表（哪些板卡 OnLine、各多少数量） | 通道总数必须 ≥ .sig 用到的 |
| `X.tim` | 波形表（`TimingName,Period,Signal,WFC,Evt0..Evt3`） | **两套编号**：WFC 槽位名 vs Evt 序号 |
| `X.pat` | pattern 索引（名字→CSV 相对路径） | 注册了但 CSV 不存在 = 静默不加载 |
| `X.tmf` | 测试流（顺序+Sbin+限值） | 参数个数须与 `CheckResultAndBin` 传参一致 |
| `Test.cpp` | 测试逻辑（导出函数） | `ST_MEAS_RESULT` 字段是 `dbValue` |
| `pattern/*.csv` | 向量（`Label,WFT,sequence,<各信号>`） | 字符集必须 ⊆ `.tim` 的 WFC 集合 |
| `Makefile` | 编译生成 `Test.dll` | `RUNNER_HOME` 双反斜杠会炸 |

## 核心工作流

### 第 1 步：读器件手册，提取限值（不许估算）

用 `pdftotext -enc UTF-8 <手册.pdf> <out.txt>` 提取文本，表格读不准时用
`pdftoppm -r 150 -png` 渲染页面后用 Read 工具看图。**每一条限值都要能指到
手册的表号行号**，例如「VOH min 4.4V @ VCC=4.5V, IO=-20µA（Table 6）」。

必须同时提取：真值表、封装选项、VIH/VIL、VOH/VOL、II/ICC、时序参数。

> **Read 工具读 /tmp 下文件要换 Windows 路径**：`C:\Users\jlin\AppData\Local\Temp\...`

### 第 2 步：核对资源可行性（别等写完代码才发现装不下）

- ST2500：160 通道 DIO（125MHz）、160 通道 PPMU（-2~6.5V）、DPS ±500mA、**无 TMU**
- **TMU 是 ST5000 才有**，ST2500 测不了振荡器频率
- 通用接口板（SE-GIB100）：14 路 DIO Inout + 4 路 DPS
- 算一遍：`所需 DIO 数 vs 板卡通道数`。例如 74HC138 = 6 输入 + 8 输出 = 14 路，正好占满

### 第 3 步：设计 `.sig` / `.grp`（分组是后续所有测试的前提）

`.grp` 至少要有：全部信号组、单脚组（做 VIH/VIL 必需）、"其余脚"组。

**为什么必须有单脚组**：`pinlevel.SetVih(v)` 是**组级**设置。要只给 A0 施加
3.15V 而其它脚保持 4.5V，A0 必须单独成组。

### 第 4 步：写 `.tim`——WFC 槽位是理解 Pattern 的钥匙

`.tim` 一行 = 一个 WFC 槽位（该信号的第几种波形）。列含义：

```
TimingName,Period,Signal,WFC,Evt0 Event,Evt0 Expr,Evt1 Event,Evt1 Expr,...
WFT1,1000ns,CLK,0,D,0ns,,,,,,        ← 槽位0：D@0ns，恒低
,,,1,D,0ns,U,2000ns,D,3996ns,,,,     ← 槽位1：一个时钟脉冲
,,,H,H,900ns,,,,,                    ← 槽位H：900ns 采样，期望高
```

- `Event` 列：`U`/`D`/`Z` = 驱动边沿（最多 4 个，D0~D3）；`H`/`L`/`X` = 比较（**只有 1 个，R0**）
- `Expr` 列：时刻，带 `ns` 后缀
- 硬件规则：驱动最多 4 边沿 → L/H/X 槽位**必然只填 Evt0**
- 槽位名可自定义（0/1/X/Z/H/L），**编号不必连续，顺序也不影响功能**

**两套编号别搞混**（最易卡住的点）：

| | WFC 列 | Evt0~Evt3 列 |
|---|---|---|
| 是什么 | 槽位的**名字** | 槽位内部的**第几个边沿** |
| 位置 | 行首，每行一个 | 列头，固定四列 |
| 数量 | 每信号任意多个 | 每行最多 4 个 |

"只有 Evt0" ≠ "只有一个槽位"。空格只表示该槽位用不到那么多边沿。

### 第 5 步：写 pattern CSV

表头 `Label,WFT,sequence,<信号1>,<信号2>,...`。

- Pattern 里填的字符是**槽位名**，不是电平！
- **同一字符在不同信号列含义完全不同**：`CLK=1` 可能是一个时钟脉冲，`CS=1` 才是恒高
- 换信号格式 = 改 `.tim` 的槽位定义，**不是改 Pattern**
- 功能测试必须**同时比较全部输出脚**，否则脚间短路/浮空测不出

### 第 6 步：写 `Test.cpp`

要点：

- `ST_MEAS_RESULT` 的字段是 **`dbValue`**，没有 `value`/`valid`
- `ST_DIO_RESULT` 只有 `ulSite` 和 `bPass`
- `pinlevel` 对象类型是 **`PLVL`**，它有 `VoltClamp` 和 `Connect`
- 每个测项必须调 `CheckResultAndBin(0, 结果数组, 参数个数)`，否则**测出来的值不会被判限**
- 低有效器件（74HC138、74HCxx）测 VOH/VOL 的激励与常规相反：测 VOL 要让该路**被选中**，测 VOH 要让该路**不被选中**
- PPMU 测电流：先 `VoltForce` 加压再 `CurrForce` 测，或直接 `CurrForce` 测漏电

### 第 7 步：写 `.tmf`（限值逐条对应手册）

`.tmf` 是 JSON。`SiteList[0].FuncList[]` 每项：
`FuncNumber, FuncName, FuncDesc, LoopCount, Sbin, Hbin, Results, ResultAnalysis[]`。
`ResultAnalysis` 每项：`ParamName, ParamNumber, Min, Max, Unit`。

**参数总数必须等于 `Test.cpp` 里该函数的判限参数数**。注意 `CheckResultAndBin`
有 6 个重载，一个函数内可**多次调用**并用 `ulParamStartID` 划分区间
（官方 ADC0832 的 `OS_TEST` 就是 7+6 两段）。核对时把函数内所有带 count
的调用求和再比对。置 Bin 函数用 `binObj.SetBin(1)` 而非判限。

详见 `references/compile-and-api.md`。

### 第 8 步：编译（本机有坑，见下）

优先用 ST-IDE 内部构建（等价于 `make -k`）。命令行编译用 `build.bat`。

## 本机三大坑（务必先读）

### 坑 1：`D:\MINI-ATE\mingw64` 的 g++ 不能直接调用

直接调 `g++` → `cc1plus.exe` 崩溃 `0xC0000005`，**无任何报错输出，退出码 1**。
文件与 DLL 依赖都完好，是 2018 年 MSYS2 构建与现代 Windows 不兼容。

- **ST-IDE 里编译没问题**：IDE 的 CDT makeBuilder 调的是 `make`，`make` 是 MSYS2
  程序会正确设置子进程环境
- **命令行必须经由 `make`**，或换用现代 MinGW-w64 工具链

### 坑 2：Makefile 的 `RUNNER_HOME` 双反斜杠

各案例 Makefile 里 `RUNNER_HOME = d:\\MINI-ATE\\runner`，GNU make 会把 `\\`
转义掉导致 `exist` 判断失败 → `$(error Folder ... does not exist)`。
**改成正斜杠 `d:/MINI-ATE/runner`**。

### 坑 3：链接项不能含 `-llibCommon` / `-lShmoo`

runner 目录下只有对应 DLL，**没有这两个 `.a` 导入库**，加了会链接失败。
以 IDE 生成的 Makefile（`workspace\ADC0832_FT_EDU_V3\Makefile`）为准。

### 备用工具链

`%USERPROFILE%\.workbuddy\binaries\mingw64\ucrt64\`（GCC 16.2.0 ucrt64）。
来源：清华 TUNA 镜像 `https://mirrors.tuna.tsinghua.edu.cn/msys2/mingw/ucrt64/`（9MB/s）。
必需包：gcc, gcc-libs, binutils, headers-git, crt-git, winpthreads-git,
libwinpthread-git, libmangle-git, zstd, gmp, mpfr, isl, zlib, mpc, gettext-runtime,
libstdc++（包名 URL 编码为 `libstdc%2B%2B`）。

**缺任何一个 `libisl-23.dll` / `libmpc-3.dll` / `libgcc_s_seh-1.dll` / `libintl-8.dll`
cc1plus 就崩**。`default-manifest.o` 要自己造（gcc 编译空 C 文件）并放到
`ucrt64/x86_64-w64-mingw32/bin/`。解包用 `zstandard` + `tarfile`。

## ST-IDE 导入变灰的根因（反编译实证）

**症状**：Import 对话框里工程名是灰色、无法勾选。

**根因**（`WizardJobImportPage` 反编译源码，两处判据）：

1. `isProjectInWorkspacePath(name)` —— 只要 `D:\MINI-ATE\workspace\<name>`
   **目录存在**（哪怕 IDE 从没注册过它），`hasConflicts` 就为 true → 灰色
2. `isProjectInWorkspace(name)` —— 该名字已在 workspace 注册表
   （`.metadata\.plugins\org.eclipse.core.resources\.projects\<name>`）里 → 灰色

灰色条目在 `addCheckStateListener` 里被强制 `setChecked(false)`，并在
`ProjectLabelProvider.getForeground` 里被涂成系统灰色（color 15）。

**还有一条**：`collectProjectFilesFromDirectory` 只收录满足
`jobName.equalsIgnoreCase(父目录名)` 的 `.job` 文件。**`.job` 文件名必须与
所在目录名一致**（`HC138_v1.job` 必须在 `HC138_v1\` 目录下），否则连列表都进不去。

**解决办法**：

- 导入前确保 `D:\MINI-ATE\workspace\` 下**没有**同名目录
- 或换个工程名（实测改名成 `HC138_V2` 即可正常导入）
- 手动部署到 workspace 会**占位**，导致之后 IDE 导入变灰——这是同一枚硬币的两面

## 交叉校验（建完必跑）

`scripts/validate_project.py <工程目录> [--truth-table]` 会一次跑完：

1. Pattern 字符 ⊆ `.tim` WFC 集合（字符集硬约束）
2. `.pat` 里每个 path 都有对应 CSV（未注册的文件只作提示）
3. `.tmf` 函数名 ↔ `Test.cpp` 导出函数
4. `.tmf` 参数数 ↔ 实际判限调用数（含多次调用求和、SetBin 特例）
5. 译码真值表自洽性（`--truth-table`）

已在 **5 个工程**（HC138_v1 / ADC0832 / HK32F031 / HK24C02 / LM358P）回归通过。
它还能查出官方工程里真实存在的问题——例如 HK32F031 有 16 个 pattern
未在 `.pat` 注册（改了不生效）。

## 导入预检

`scripts/check_import_ready.py <工程目录>` 在打开 IDE 之前就复现 IDE 的
灰色判定逻辑，避免在 GUI 里反复试。

## 常用排查命令

```bash
# 提取 PDF 文本 / 渲染页面
pdftotext -enc UTF-8 <in.pdf> <out.txt>
pdftoppm -f 11 -l 11 -r 200 -png <in.pdf> <prefix>

# 解包官方 CHM 手册
# PowerShell: hh.exe -decompile <dir> "<chm>"   （7-Zip 不可用）

# 反编译 IDE 插件看真实逻辑
java -jar cfr.jar "D:/MINI-ATE/plugins/com.urt.mini.application_*.jar" --outputdir dec --silent true

# 检查导出符号
"D:/MINI-ATE/mingw64/bin/objdump.exe" -p Test.dll | grep -A 40 "Export Address Table"
```

## 交付前检查清单

- [ ] 所有限值都能指到手册表号
- [ ] `validate_project.py` 全绿
- [ ] `Test.dll` 导出函数齐全（Runner 按名字调用，缺一个就调不到）
- [ ] `Makefile` 的 `RUNNER_HOME` 是正斜杠
- [ ] `build.bat` / `run_all.bat` 是 **CRLF 行尾**（LF 会让 cmd 解析错乱）
- [ ] 导入前确认 workspace 下无同名目录

## 安全提醒

在 bash 里 `cd <长路径> && rm -f xxx` 若路径含中文/括号，会导致 cwd 解析异常，
**可能误删整个目录**。删除前先 `ls` 确认 cwd，或一律用绝对路径。
