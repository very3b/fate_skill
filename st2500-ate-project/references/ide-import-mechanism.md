# ST-IDE 导入机制详解（反编译实证）

本文所有结论来自对 `D:\MINI-ATE\plugins\com.urt.mini.application_*.jar` 中
`com/urt/mini/ui/core/WizardJobImportPage.java` 的 CFR 反编译，以及对
`org.eclipse.ui.ide_*.jar` 中 `org/eclipse/ui/internal/wizards/datatransfer/
WizardProjectsImportPage.java`（父类）的分析。

## 复现方法

```bash
# 1. 取反编译器
#    CFR: https://repo1.maven.org/maven2/org/benf/cfr/0.152/cfr-0.152.jar
#    (清华 TUNA 的 maven 镜像没有这个包，走 Maven Central 反而快)

# 2. 反编译
java -jar cfr.jar "D:/MINI-ATE/plugins/com.urt.mini.application_1.0.0.202210210823.jar" \
     --outputdir dec --silent true

# 3. 关键文件
dec/com/urt/mini/ui/core/WizardJobImportPage.java
dec/com/urt/mini/ui/core/ImportJobWizard.java
dec/com/urt/mini/ui/core/MakefileJobGenerator.java
```

## 导入流程全貌

```
用户点 Import
  → ImportJobHandler
      → ImportJobWizard (extends Wizard, implements IImportWizard)
          → WizardJobImportPage (extends Eclipse 的 WizardProjectsImportPage)
              ├─ collectProjectFilesFromDirectory()  ← 发现 .job 文件
              ├─ ProjectRecord.setProjectName()        ← 判定 invalid
              └─ getProjectRecords()                   ← 判定 hasConflicts
```

## 阶段 1：发现候选工程（collectProjectFilesFromDirectory）

```java
String dotProject = ".job";       // 注意：不是 ".project"！
...
} else if (fileName.endsWith(".job") && file.isFile()) {
    String jobName = fileName.substring(0, fileName.lastIndexOf("."));
    if (checkJobProjectFormat(file.getParent())
        && jobName.equalsIgnoreCase(file.getParentFile().getName())) {
        files.add(file);
    }
}
```

**两个硬条件**：

1. `checkJobProjectFormat(父目录)` —— 父目录路径不能等于 workspace 根路径。
   即不能从 workspace 目录本身去"导入"（那是打开，不是导入）。
   ```java
   private static boolean checkJobProjectFormat(String jobParentPath) {
       IPath location = Platform.getLocation();
       File file = location.toFile();
       String workSpacePath = file.getPath();
       return !workSpacePath.equals(jobParentPath);
   }
   ```
2. **`jobName.equalsIgnoreCase(父目录名)`** —— `.job` 文件名去掉扩展名后，
   必须等于它所在的目录名。`HC138_v1.job` 必须在 `HC138_v1\` 目录下。
   不满足则**连列表都进不去**（不是灰色，是看不见）。

另外递归时会跳过名为 `.metadata` 的目录。

## 阶段 2：判定 invalid（ProjectRecord.setProjectName）

```java
private void setProjectName() {
    this.projectName = this.projectSystemFile.getParentFile().getName();
    String projectSystemFileName = this.projectSystemFile.getName();
    String jobName = projectSystemFileName.substring(0, projectSystemFileName.lastIndexOf("."));
    if (!jobName.equalsIgnoreCase(this.projectName)) {
        this.projectName = DataTransferMessages.WizardProjectsImportPage_invalidProjectName;
        this.isInvalid = true;              // ← 灰色
    } else {
        // 构造 IProjectDescription，natures 固定为 4 个：
        //   com.urt.mini.application.atenature
        //   org.eclipse.cdt.core.cnature
        //   org.eclipse.cdt.core.ccnature
        //   MakeProjectNature.NATURE_ID
        // builder = MakeBuilder.BUILDER_ID
        // arguments: enableFullBuild=true, stopOnError=false, errorOutputParser=...
    }
}
```

**重要**：`.project` / `.cproject` 文件是 IDE 在导入时**自动生成**的，
不依赖手写的那份。手工预置的 `.project` 只是给 IDE 打开已有目录时用。

## 阶段 3：判定 hasConflicts（灰色）—— 这是"import 为灰色"的真凶

```java
// getProjectRecords()
String projectName = this.selectedProjects[i].getProjectName();
this.selectedProjects[i].hasConflicts =
      this.isProjectInWorkspacePath(projectName) & !this.isFromWorkspace(this.selectedProjects[i].projectSystemFile)
    || this.isProjectInWorkspace(projectName);
```

三个判据：

```java
private boolean isProjectInWorkspacePath(String projectName) {
    IPath wsPath = ResourcesPlugin.getWorkspace().getRoot().getLocation();
    IPath localProjectPath = wsPath.append(projectName);
    return localProjectPath.toFile().exists();      // ← 只要目录存在就 true
}

private boolean isProjectInWorkspace(String projectName) {
    for (IProject p : getProjectsInWorkspace()) {
        if (projectName.equals(p.getName())) return true;
    }
    return false;
}

private boolean isFromWorkspace(File projectSystemFile) {
    File parentFile = projectSystemFile.getParentFile();
    String projectName = parentFile.getName();
    IPath prjPath = ResourcesPlugin.getWorkspace().getRoot().getLocation().append(projectName);
    File prjFile = prjPath.toFile();
    if (!this.isProjectInWorkspace(projectName) && prjFile.equals(parentFile)) {
        this.copyFiles = false;
        return true;
    }
    this.copyFiles = true;
    return false;
}
```

### 结论

| 情况 | 结果 |
|------|------|
| `workspace\<name>` 目录存在（哪怕 IDE 从没注册过） | **灰色** |
| `<name>` 已在 IDE 注册表（`.metadata\...\projects\<name>`） | **灰色** |
| `.job` 文件名 ≠ 所在目录名 | **列表里根本看不到** |
| 以上都不满足 | 正常可勾选 |

## 灰色是怎么呈现的

```java
// 勾选监听器：invalid / conflict 强制取消勾选
this.projectsList.addCheckStateListener(event -> {
    ProjectRecord element = (ProjectRecord)event.getElement();
    if (element.hasConflicts || element.isInvalid) {
        this.projectsList.setChecked((Object)element, false);
    }
    ...
});

// 标签渲染：涂系统灰色（color 15 = SWT.COLOR_GRAY）
public Color getForeground(Object element) {
    ProjectRecord projectRecord = (ProjectRecord)element;
    if (projectRecord.hasConflicts || projectRecord.isInvalid) {
        return getShell().getDisplay().getSystemColor(15);
    }
    return null;
}
```

提示文案（`DataTransferMessages`）：

| key | 文案 |
|-----|------|
| `WizardProjectsImportPage_projectsInWorkspace` | Some projects cannot be imported because they already exist in the workspace |
| `WizardProjectsImportPage_projectsInvalid` | Some projects cannot be imported because their project description file is corrupted |
| `WizardProjectsImportPage_projectsInWorkspaceAndInvalid` | ...already exist in the workspace or their project description file is corrupted |
| `WizardProjectsImportPage_invalidProjectName` | Invalid Project |
| `WizardProjectsImportPage_noProjectsToImport` | No projects are found to import |

## 实战案例：为什么 HC138_v1 灰色而 HC138_V2 正常

2026-10-21 的实际状态：

```
D:\MINI-ATE\workspace\
├── ADC0832_FT_EDU_V3\        ← 已注册
├── HK24C02_...\
├── HK32F031F4P6_FT_EDU_V3\
├── LM358P_FT_EDU_V3\
├── HC138_v1\                 ← 我用 run_all.bat 手动部署的 → 占位
└── HC138_V2\                 ← 用户改名新建的 → 可导入
```

`HC138_v1` 命中了 `isProjectInWorkspacePath`（目录存在）**和**
`isProjectInWorkspace`（注册表里有记录）→ 两个条件都为真 → 灰色。

`HC138_V2` 两个条件都不满足 → 正常可导入。

**教训**：用脚本把工程手动拷到 workspace 会"占位"，导致之后在 IDE 里
无法正常导入同一个工程。这两者是同一枚硬币的两面——要么脚本部署 + IDE 打开，
要么 IDE 导入，不要两条路都走。

## 预检脚本

`scripts/check_import_ready.py` 用完全相同的规则做预检：

```bash
python check_import_ready.py "D:/.../HC138_v1"
```

输出示例：

```
  .job: HC138_v1.job
    OK  文件名与目录名一致
    [X] workspace 下已存在同名目录 -> 导入列表里会显示为灰色不可勾选
        D:\MINI-ATE\workspace\HC138_v1
        解决：① 改名导入（如 HC138_v1_V2）② 或先移走该目录
    [X] 'HC138_v1' 已在 IDE 注册表中 -> 同样显示为灰色
    [!] jobDir 用了双斜杠 'D://MINI-ATE//workspace//HC138_v1'
        IDE 生成的格式是反斜杠：D:\MINI-ATE\workspace\<name>
```

## .job 文件的正确格式（IDE 自己生成的样式）

`MakefileJobGenerator.populateModel()` 是 IDE 生成 .job 的地方：

```java
String jobDir = project.getLocation().toString();
IPath jobPath = project.getFile(new Path("/" + project.getName() + ".job")).getLocation();
String home = CommonUtils.getHome().replace("\\", "/");
SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd hh:mm:ss");
model.put("jobDir", jobDir);
model.put("jobFilePath", jobPath.toString());
model.put("AteHomePath", home);
model.put("currentTime", date);
model.put("PROG_HOME", home);
```

`CommonUtils.getHome()` 的取值优先级：

```java
String ateHomePath = System.getenv("MINI-ATE_HOME");
if (ateHomePath == null) ateHomePath = System.getenv("MINI_ATE_HOME");
if (ateHomePath == null) ateHomePath = CommonUtils.getScWorkbenchDir();
if (ateHomePath == null) { /* Platform.getInstallLocation() */ }
```

即 **环境变量 `MINI-ATE_HOME` 优先**。本机机器级有 `MINI-ATE_HOME=d:\MINI-ATE`。

IDE 实际写出的 .job 样式（参考 `workspace\ADC0832_FT_EDU_V3\*.job`）：

```json
{
	"JOB":"2.0",
	"jobDir":"D:\\MINI-ATE\\workspace\\ADC0832_FT_EDU_V3",
	"jobFilePath":"D:\\MINI-ATE\\workspace\\ADC0832_FT_EDU_V3\\ADC0832_FT_EDU_V3.job",
	"Name":"ADC0832_FT_EDU_V3",
	"Date":"Tue Jun 02 18:46:00 CST 2020",
	"ResDef":"ADC0832_FT_EDU_V3.res",
	"SigMap":"ADC0832_FT_EDU_V3.sig",
	"Pattern":"ADC0832_FT_EDU_V3.pat",
	"Timing":"ADC0832_FT_EDU_V3.tim",
	"TestProg":{
		"Src":[],
		"IncDir":["./AWG/", "./AWG\\awd/", "./datalog/"]
	},
	"Library":"Test.dll",
	"Makefile":"Makefile",
	"TMF":"ADC0832_FT_EDU_V3.tmf",
	"AteHomePath":"d:\\MINI-ATE",
	"SigGroup":"ADC0832_FT_EDU_V3.grp",
	"lotId":"defaule-fbd14a"
}
```

要点：
- **反斜杠**（JSON 里写成 `\\`），不要用正斜杠，更不要 `//`
- 用 **Tab** 缩进
- `Date` 格式 `yyyy-MM-dd hh:mm:ss`
- `AteHomePath` 末段无斜杠：`d:\MINI-ATE`
