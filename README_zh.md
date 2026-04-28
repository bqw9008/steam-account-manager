# Steam 账号管理器

### [中文](README_zh.md) | [English](README.md)

Steam Account Manager 是一个本地 Windows 桌面工具，用于管理多个 Steam 账号，并可快速对选中的账号发起登录操作。

当前界面基于 PySide6 构建。旧版 Tkinter 实现已归档到 `legacy/` 中，仅作为参考；`main.py` 只启动 PySide6 界面。

![界面](imgs/main_page.png)

---

## 功能特性

- 本地账号管理（使用 JSON 持久化存储）
- 支持自定义账号分组、分组筛选和批量设置分组
- 支持搜索、状态/分组筛选和排序选择，并会持久化账号列表筛选设置
- 支持按最近使用、5E 分段、封号/冻结状态排序
- Steam 登录信息为核心必填信息；5E 昵称和 5E 分段为可选信息，并会直接显示在账号列表中
- 支持一键赛季重置为未定级，并把上赛季分段追加到备注
- 支持手动填写冻结截止时间，并显示大致剩余时间
- 支持账号的创建、编辑、删除及批量删除
- 支持对选中账号进行批量状态更新
- 支持单行或多行账号文本的快速导入
- 批量导入支持预览后再保存
- 根据 `login_name` 自动处理重复导入
- 更安全的导入覆盖逻辑：空字段不会覆盖已有的 `last_login` 或备注
- 自动检测 Steam 路径（也支持手动选择）
- 支持从主列表或已有账号详情弹窗中直接发起 Steam 登录
- Steam 登录尝试成功启动后自动更新最后登录时间
- Steam 登录面板支持可配置的关闭策略：
  - 优雅关闭（先尝试正常关闭，必要时询问是否强制关闭）
  - 直接强制关闭
- 根据 Windows 系统主题自动切换浅色/深色界面

---

## 运行环境

- Windows 系统
- Python 3.10 及以上
- PySide6

安装依赖：

```powershell
pip install -r requirements.txt
```

如果使用 Conda：

```powershell
conda activate py
python -m pip install -r requirements.txt
```

当前项目验证命令默认使用 Conda 的 `py` 环境，例如：

```powershell
conda run -n py python -m unittest discover -s tests -v
```

---

## 运行方式

```powershell
python main.py
```

`main.py` 启动 `qt_app.py`（PySide6 界面）。

如果未安装 PySide6，程序会报错并提示安装。已归档的 Tkinter 界面不再由入口加载，也不用于发布打包。

---

## 数据文件

运行时数据存储在本地 `data/` 目录：

```text
data/accounts.json
data/settings.json
```

这些文件已被 Git 忽略，因为其中可能包含：

- 账号名
- 密码
- 邮箱地址
- 手机号
- Steam 路径
- 账号列表搜索词、状态筛选、分组筛选、排序方式等本地配置
- 其他本地配置等敏感信息

---

## 导入格式说明

导入器支持较为宽松的账号文本格式，支持识别如下字段标签：

- `5E账号`
- `5E密码`
- `昵称`
- `steam账号`
- `密码`
- `邮箱账号` / `油箱账号`
- `邮箱地址` / `油箱地址`
- `手机号`

支持两种格式：

- 每行一个账号
- 多行组成一个账号块

解析出的 5E 昵称会保存到独立的 `five_e_nickname` 字段，并在账号列表中作为单独列显示。旧数据如果还只在备注里保留 `5E昵称: ...`，界面也会继续兜底读取并显示。

账号的核心必填信息是 Steam 登录名和 Steam 密码；5E 相关信息都是可选项，可以后续补充。

---

## 安全说明

本工具仅用于本地个人使用，以及低价值账号管理场景。

需要注意的安全问题：

- 账号密码以明文形式存储在本地 JSON 文件中
- 当前登录方式使用：
  ```
  steam.exe -login <login_name> <password>
  ```
- 命令行参数可能被本地诊断工具或其他进程获取
- 请勿提交、上传或分享以下文件：
  - `data/accounts.json`
  - `data/settings.json`
  - 原始导入文件（如 `accounts.txt`）

如果需要更高安全性，请在使用前自行增加加密存储机制。

---

## 打包说明

如果需要打包为 Windows 可执行文件，推荐使用 PyInstaller。

推荐单文件构建方式：

```powershell
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name SteamAccountManager --icon imgs\gnuhl-7oo8y-001.ico --add-data "imgs\gnuhl-7oo8y-001.ico;imgs" --exclude-module tkinter --exclude-module legacy main.py
```

构建产物：

```text
dist/
└─ SteamAccountManager.exe
```

用户可直接运行 `SteamAccountManager.exe`。首次启动时，程序会在 exe 同目录自动创建运行时数据：

```text
data/
├─ accounts.json
└─ settings.json
```

⚠️ 注意：
不要将真实账号数据提交到 Git，也不要将真实的 `accounts.json` 或 `settings.json` 打包进发布文件。

---

## 项目结构

```text
main.py              程序入口（启动 PySide6 界面）
qt_app.py            当前 PySide6 桌面界面
legacy/tk_app.py     已归档的 Tkinter 界面参考（不由 main.py 使用）
models.py            SteamAccount 数据模型
repositories.py      JSON 读写（带校验与原子写入）
freeze_utils.py      冻结截止时间解析与剩余时间显示
text_importer.py     账号文本解析逻辑
system_utils.py      Windows / Steam 工具函数
config.py            路径、状态定义、翻译、主题配置
steam_ui_probe.py    用于分析 Steam 登录界面的辅助脚本
data/                本地运行数据（已被 Git 忽略）
```

---

## 说明

这是一个个人本地工具，并非 Steam 官方工具，请自行承担使用风险。
