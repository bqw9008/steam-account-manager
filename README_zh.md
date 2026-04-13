# Steam 账号管理器

Steam Account Manager 是一个本地 Windows 桌面工具，用于管理多个 Steam 账号，并可快速对选中的账号发起登录操作。

当前界面基于 PySide6 构建。旧版的 Tkinter 实现仍保留在 `app.py` 中作为备用/参考，但默认由 `main.py` 启动 PySide6 界面。

![界面](imgs/main_page.png)

---

## 功能特性

- 本地账号管理（使用 JSON 持久化存储）
- 支持搜索与状态筛选
- 支持账号的创建、编辑、删除及批量删除
- 支持对选中账号进行批量状态更新
- 支持单行或多行账号文本的快速导入
- 批量导入支持预览后再保存
- 根据 `login_name` 自动处理重复导入
- 更安全的导入覆盖逻辑：空字段不会覆盖已有的 `last_login` 或备注
- 自动检测 Steam 路径（也支持手动选择）
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

---

## 运行方式

```powershell
python main.py
```

`main.py` 默认启动 `qt_app.py`（PySide6 界面）。

如果未安装 PySide6，程序会报错并提示安装。  
你也可以手动启用 Tkinter 备用界面：

```powershell
$env:SAM_ALLOW_TKINTER_FALLBACK="1"
python main.py
```

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
- 本地配置等敏感信息

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

推荐构建方式：

```powershell
pip install pyinstaller
pyinstaller --noconsole --onedir --name SteamAccountManager main.py
```

推荐目录结构：

```text
SteamAccountManager/
├─ SteamAccountManager.exe
├─ _internal/
└─ data/
   ├─ accounts.json
   └─ settings.json
```

⚠️ 注意：
不要将真实账号数据提交到 Git，也不要将真实的 `accounts.json` 打包进发布文件。

---

## 项目结构

```text
main.py              程序入口（启动 PySide6 界面）
qt_app.py            当前 PySide6 桌面界面
app.py               旧版 Tkinter 界面（备用/参考）
models.py            SteamAccount 数据模型
repositories.py      JSON 读写（带校验与原子写入）
text_importer.py     账号文本解析逻辑
system_utils.py      Windows / Steam 工具函数
config.py            路径、状态定义、翻译、主题配置
steam_ui_probe.py    用于分析 Steam 登录界面的辅助脚本
data/                本地运行数据（已被 Git 忽略）
```

---

## 说明

这是一个个人本地工具，并非 Steam 官方工具，请自行承担使用风险。