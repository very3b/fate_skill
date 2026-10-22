# fate_skill

WorkBuddy / Claude Code 技能仓库。

每个技能是一个独立目录，含 `SKILL.md`（入口）+ `scripts/`（可执行脚本）+
`references/`（按需加载的参考资料）。

## 技能列表

### `st2500-ate-project` — 加速科技 ST2500/ST5000 ATE 测试工程

为加速科技 ST2500 / ST5000 ATE 测试机**新建、调试或修复**完整测试工程。

覆盖的工程文件（缺一不可）：

| 文件 | 作用 |
|------|------|
| `X.job` | 工程入口（JSON），指向其余所有文件 |
| `X.sig` | 信号→通道映射 |
| `X.grp` | 信号分组（决定 `pinlevel` 能否单独给某脚施压） |
| `X.res` | 机台资源表（板卡 OnLine 与数量） |
| `X.tim` | 波形表（TimingSet / WFC 槽位 / Evt 边沿） |
| `X.pat` | pattern 索引（名字 → CSV 相对路径） |
| `X.tmf` | 测试流（顺序 + Sbin + 限值） |
| `Test.cpp` | 测试逻辑（导出函数） |
| `pattern/*.csv` | 向量文件 |
| `Makefile` | 编译生成 `Test.dll` |

#### 核心内容

- **8 步工作流**：读手册提限值 → 核资源 → 设计分组 → 写时序 → 写 pattern
  → 写测试代码 → 写测试流 → 编译
- **Pattern / WFC 时序方法论**：两套编号体系（槽位名 vs Evt 边沿序号）、
  字符集硬约束、RZ/RO/NRZ/SBC 四种信号格式与 Wave Table 自由拼装
- **ST-IDE 导入机制**（插件反编译实证）：import 变灰的三个根因
- **编译环境**：本机 g++ 不可直接调用的原因与三条可用路径
- **测试方案方法论**：从器件手册到测试项矩阵，VIH/VIL 二分搜索测法

#### 两个实用脚本

```bash
# 工程交叉校验（5 项检查）
python st2500-ate-project/scripts/validate_project.py <工程目录> [--truth-table]

# ST-IDE 导入预检（打开 IDE 之前就发现问题）
python st2500-ate-project/scripts/check_import_ready.py <工程目录>
```

`validate_project.py` 检查：

1. Pattern 字符 ⊆ `.tim` 的 WFC 集合（硬约束，违反则运行时加载报错）
2. `.pat` 索引完整性（注册了但文件不存在 = 静默不加载）
3. `.tmf` 函数名 ↔ `Test.cpp` 导出函数
4. `.tmf` 参数数 ↔ 实际判限调用数（**漏调判限 = 测出的值不会被判限**）
5. 译码真值表自洽性

已在 5 个工程回归通过（74HC138 / ADC0832 / HK32F031 / HK24C02 / LM358P）。

#### 安装

把 `st2500-ate-project/` 整个目录复制到技能目录即可：

```bash
cp -r st2500-ate-project ~/.workbuddy/skills/          # WorkBuddy
cp -r st2500-ate-project ~/.claude/skills/              # Claude Code
```

## 资料来源

本仓库所有结论均来自以下**一手来源**，不是凭印象推断：

- 官方 API 手册 `D:\MINI-ATE\doc\ST2500&&ST5000_API_20211115_V2.4.chm`
  （第 62 章 DIO Timing / 第 63 章 DIO Pattern / 第 69 章 DIO 微指令）
- 教学课件 `2.教学课件/6.课件-数字电路模块功能介绍.pdf`（WFT 波形格式示例、
  RZ/RO/NRZ/SBC 定义）与 `4课件-集成电路基础测试原理.pdf`
- 技术手册 `1.技术手册/3.ST2500简明使用教程V3.pdf`
- **IDE 插件反编译源码**（CFR 反编译 `com.urt.mini.application_*.jar`，
  得到 `WizardJobImportPage.java` 等）——导入判定逻辑的权威依据
- 课程案例工程实测数据（6 个案例、48 个 pattern、51.7 万行向量）
