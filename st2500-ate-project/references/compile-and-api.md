# 编译环境与 API 速查

## 一、编译环境

### 本机编译器状态

| 工具链 | 路径 | 状态 |
|--------|------|------|
| MINI-ATE 自带 | `D:\MINI-ATE\mingw64` | **g++ 不可直接调用**（cc1plus 崩溃） |
| 备用（已装） | `%USERPROFILE%\.workbuddy\binaries\mingw64\ucrt64\` | GCC 16.2.0 ucrt64，可用 |
| make | `D:\MINI-ATE\mingw64\bin\make.exe` | 可用（MSYS2 程序，能正确设子进程环境） |

### cc1plus 崩溃的准确症状

```
$ d:\MINI-ATE\mingw64\bin\g++.exe -c test.cpp
（无任何输出）
退出码 = 1
```

- 进程是 `cc1plus.exe` 自己崩的，**退出码 0xC0000005（访问冲突）**
- 依赖 DLL 全部齐全、文件完整（24.8MB）——是 2018 年 MSYS2 构建与现代 Windows 不兼容
- `cc1.exe`（C 前端）在同一偏移崩溃，说明是 GCC 前端运行时的环境问题

### 为什么 ST-IDE 里能编译

IDE 的 CDT makeBuilder 调的是 `make`（MSYS2 程序），它会正确设置子进程
的 DLL 搜索路径。**直接调 `g++` 绕过 make 就会崩。**

验证过：同一目录、同一命令，ADC0832 能编而 HC138 不能 —— 四个交叉组合
（含"HC138 目录 + ADC 代码"）全部失败，证明**与代码无关，是环境问题**。

### 三种可用的编译路径

```bash
# 路径 A：ST-IDE 内右键 Build Project（最省心）

# 路径 B：命令行经由 make
export PATH="/d/MINI-ATE/mingw64/bin:$PATH"
make -k

# 路径 C：工程自带的 build.bat（自动探测工具链 + 校验导出函数）
cmd.exe /c build.bat
```

`build.bat` 的逻辑：先编译一个空文件验证工具链真的能用，不可用就换备用链。

### 备用工具链搭建（可复现）

```bash
BASE="https://mirrors.tuna.tsinghua.edu.cn/msys2/mingw/ucrt64/"
# 必需包（版本用正则取最新）：
#   gcc, gcc-libs, binutils, headers-git, crt-git, winpthreads-git,
#   libwinpthread-git, libmangle-git, zstd, gmp, mpfr, isl, zlib,
#   mpc, gettext-runtime, libstdc++（URL 编码为 libstdc%2B%2B）
```

解包用 Python（MSYS2 包是 `.pkg.tar.zst`）：

```python
import zstandard as zstd, tarfile, io
dctx = zstd.ZstdDecompressor()
with open(pkg, 'rb') as fh:
    data = dctx.stream_reader(fh).read()
with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as tf:
    tf.extractall(OUT, filter='data')
```

**两个必须注意的坑**：

1. `libisl-23.dll` / `libmpc-3.dll` / `libgcc_s_seh-1.dll` / `libintl-8.dll`
   缺任何一个，cc1plus 就崩（用 PE 导入表解析找出依赖，别猜）
2. `default-manifest.o` 不在包里，要自己造：
   ```bash
   gcc -c empty.c -o ucrt64/x86_64-w64-mingw32/bin/default-manifest.o
   ```

### Makefile 三个必查项

```makefile
RUNNER_HOME = d:/MINI-ATE/runner      # ① 正斜杠！双反斜杠会被 make 转义掉
                                          #    → d://MINI-ATE/runner → exist 失败
                                          #    → $(error Folder ... does not exist)
```

② 链接项**不能**含 `-llibCommon` 和 `-lShmoo`
   —— runner 目录下只有 `libCommon.dll` / `libShmoo.dll`，**没有 `.a` 导入库**。

③ 链接项清单（以 IDE 生成的 `workspace\ADC0832_FT_EDU_V3\Makefile` 为准）：

```
-lsetupapi -lkernel32 -luser32 -lgdi32 -lwinspool -lcomdlg32 -ladvapi32
-lshell32 -lole32 -loleaut32 -luuid -lodbc32 -lodbccp32
-Ld:/MINI-ATE/runner -lproject -lTester -lBinDef -lUsrApi -lWaveCalc
-shared -Wall -Wl,-subsystem,windows -mthreads -fPIC -DINTERFACE_EXPORTS -o Test.dll
```

### Windows 批处理脚本的坑

| 问题 | 现象 | 解法 |
|------|------|------|
| LF 行尾 | cmd 报 `'xx' is not recognized` | 转成 **CRLF** |
| `for %%P in (多行列表)` | 语法混乱 | 改成单行 `if exist` 链 |
| for 循环里用 `!VAR!` | 展开为空 | 加 `setlocal enabledelayedexpansion` |
| for 循环尾部多跑一次空参数 | 误报 MISSING | 子过程加 `if "%~1"=="" goto :eof` |
| `reg.exe` | 被安全策略拦截 | 避开注册表，改用环境变量 |
| `cmd.exe` 从 Bash 调 | 被拦 | 用 PowerShell 工具 |

### 验证产物

```bash
"D:/MINI-ATE/mingw64/bin/objdump.exe" -p Test.dll | \
  sed -n '/Ordinal\/Name Pointer/,/^$/p'
```

Runner 按**名字**调用导出函数，缺一个就调不到。标准清单：

```
ProjectInit  ProjectReset  ProjectReuse  site_init  site_reset
<各测试项函数>  SetPassBin
```

## 二、API 速查

### 头文件位置

`D:\MINI-ATE\runner\inc\`：
- `usrInterface.h` —— 主接口（USR、PPMU、DPS、PLVL、DIO…）
- `usrDataType.h` —— 数据结构（`ST_MEAS_RESULT` 等）
- `Bindef.h` —— `CheckResultAndBin` 等

### 关键结构体

```cpp
// ST_MEAS_RESULT —— 字段是 dbValue，没有 value / valid
struct ST_MEAS_RESULT {
    double dbValue;       // 测量值
    // ...
};

// ST_DIO_RESULT —— 只有两个成员
struct ST_DIO_RESULT {
    unsigned long ulSite; // site 号
    bool bPass;           // 是否通过
};
```

### PLVL（pinlevel 对象）

`pinlevel` 的类型是 **`PLVL`**，可用方法：
`Signal()` `SetMode()` `SetVih()` `SetVil()` `SetVoh()` `SetVol()`
`VoltClamp()` `Connect()` `Execute()`

```cpp
// ST2500 手册里的标准用法
pinlevel.Signal("X").SetMode("DIO")
    .SetVih(dbVoltage)      // 驱动高电平 = dbVoltage
    .SetVil(0)              // 驱动低电平 = 0
    .SetVoh(dbVoltage*0.7)
    .SetVol(dbVoltage*0.3)
    .Execute();
```

**关键语义**：`SetVih(v)` 设的是「**当这个脚驱动高时，电平是多少**」——
它是**电平字典**，不是当前电平。Pattern 里写 `1` 用 `SetVih` 的值，
写 `0` 用 `SetVil` 的值。

→ 所以做 VIH/VIL 扫描时，**被测脚必须单独成组**（`SetVih` 是组级设置）。

### PPMU

`VoltForce` / `CurrForce` / `CurrRange` / `VoltClamp` / `CurrClamp` / `Measure`

- 测漏电流：`VoltForce` 加压 → `CurrForce` 测 → 读 `dbValue`（单位 µA）
- 测开路/短路：施加 ±100µA，看压降

### Pattern 调用

```cpp
dio.Pattern("XXX");   // 加载并运行 .pat 中注册的名为 XXX 的 pattern
```

`.pat` 索引格式：`序号,,名字,编号,true,相对路径,`

### 判限与分 Bin

`Bindef.h` 第 87~102 行有 **6 个重载**：

```cpp
// ① 带显式个数（最常用）
ULONG CheckResultAndBin(ULONG ulParamStartID, vector<ST_MEAS_RESULT> comm_result, ULONG ulParamCount);
// ② 不带个数（个数由数组长度决定）
ULONG CheckResultAndBin(ULONG ulParamID, vector<ST_MEAS_RESULT> comm_result);
ULONG CheckResultAndBin(ULONG ulParamID, vector<ST_DIO_RESULT> comm_result);
// ③ 单值
ULONG CheckResultAndBin(ULONG ulParamID, SITE_DOUBLE site_value);
ULONG CheckResultAndBin(ULONG ulParamID, SITE_LONG site_value);
// ④ 带限值（直接在代码里给上下限）
ULONG CheckResultAndBin(ULONG ulParamID, const SITE_DOUBLE& v, double low, double high, string unit = "");
```

**一个测项函数内可以多次调用**，用 `ulParamStartID` 划分参数区间。
官方 ADC0832 的 `OS_TEST` 就是两段：

```cpp
binObj.CheckResultAndBin(0,  N_PPMU_RESULT, 7);   // 参数 0~6
binObj.CheckResultAndBin(7,  P_PPMU_RESULT, 6);   // 参数 7~12
```

→ 所以核对限值个数时，要**把函数内所有带 count 的调用的 count 求和**，
再与 `.tmf` 的 `ResultAnalysis` 条目数比对。

**置 Bin 函数用 `SetBin` 而不是判限**：

```cpp
void SetPassBin() {
    binObj.SetBin(1);      // 不是 CheckResultAndBin
    ...
}
```

这类函数在 `.tmf` 里通常也有一条占位的 `ResultAnalysis`（`ParamName=Param`），
**不应当按"缺判限调用"报错**。

> **最重要的一条**：测项函数里**必须**有判限调用（或 `SetBin`），
> 否则测出来的值根本不会被判限——TMF 里有 6 个限值但 cpp 不传参，
> 这种 bug 从日志里完全看不出来，只能靠静态检查发现。
> `scripts/validate_project.py` 的检查项 3/4 就是查这个。

### 生命周期函数

```cpp
void ProjectInit() {}    // 工程加载
void ProjectReset() {}   // 复位
void ProjectReuse() {}   // 复用
void site_init() {}      // site 初始化
void site_reset() {}     // site 复位
```

## 三、硬件资源

### ST2500

| 资源 | 数量 | 说明 |
|------|------|------|
| DIO | 160 通道 | 最高 125MHz |
| PPMU | 160 通道 | -2 ~ 6.5V |
| DPS | 4 路（通用板） | ±500mA |
| **TMU** | **无** | 测频需 ST5000 |
| AWG / DGT / RVS / BPMU / CBIT | 按 res 配置 | |

### 通用器件接口板 SE-GIB100

- 14 路 DIO Inout + 4 路 DPS
- DUT 侧是**万用板 + DIP socket**（手册 3.3 节"装入 DUT socket 和待测芯片"）
- 所以 SO16/TSSOP16 等封装要用 **转接板**转成 DIP16

### `.res` 文件格式

```
1,OnLine,AWG_1,AWG,1
,,DGT_1,DGT,1
,,RVS_1,RVS,1
,,DPS_1,DPS,4
,,BPMU_1,BPMU,4
,,CBIT_1,CBIT,8
,,DIO_1,DIO,32
2,OnLine,AWG_2,AWG,1
...
5,OffLine,,,
```

首列是 site 号，`OnLine`/`OffLine`，然后是资源名、类型、数量。
