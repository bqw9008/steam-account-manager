# Steam Account Manager

## 项目定位

这是一个基于 Python + PySide6 的 Windows 本地桌面工具，用来管理批量 Steam 小号信息，并提供辅助登录能力。

项目特点：

- 本地运行
- 数据持久化到 JSON
- 支持中英文界面，并根据系统语言自动切换
- 支持账号列表按最近使用、封号/冻结状态排序
- 支持每个账号记录 5E 分段，并按 S > A++ > A+ > A > B++ > B+ > B > C++ > C+ > C > D 排序
- 新账号和空分段默认是 `未定级`；赛季重置可一键把所有账号设为未定级，并把已定级账号的上赛季分段追加到备注
- Steam 登录尝试成功启动后会自动更新 `last_login`，用于最近使用排序
- 主要面向 Windows 环境
- 当前登录流程基于 `steam.exe -login <login_name> <password>` 启动 Steam；如果 Steam 已在运行，会先尝试结束相关进程再重新启动
- 当前界面入口是 PySide6；旧的 Tkinter 界面代码已归档到 `legacy/`，只作为参考，不再作为回退入口

## 当前目录说明

- `main.py`
  程序入口，只启动 PySide6 界面；如果 PySide6 不可用，会提示安装依赖
- `qt_app.py`
  PySide6 主界面与主要交互逻辑
- `legacy/tk_app.py`
  已归档的旧 Tkinter 主界面与业务逻辑，仅作为参考，不参与默认入口和发布打包
- `models.py`
  账号数据模型 `SteamAccount`
- `repositories.py`
  账号数据和设置数据的读写
- `freeze_utils.py`
  冻结截止时间解析与剩余时间显示
- `config.py`
  全局配置、主题、双语文案、状态映射
- `system_utils.py`
  Windows 相关能力，包括 DPI、主题、注册表、Steam 路径检测、进程检测与结束、窗口控制、剪贴板、键盘模拟
- `text_importer.py`
  文本批量导入解析逻辑
- `steam_ui_probe.py`
  后续用于检测 Steam 登录窗口更像原生控件还是嵌入式 webview 的脚本
- `data/accounts.json`
  账号数据
- `data/settings.json`
  设置数据

## 运行方式

在项目目录下运行：

```powershell
python main.py
```

首次运行 PySide6 版本前需要安装依赖：

```powershell
pip install -r requirements.txt
```

也可以作为包入口运行，但当前主要按脚本方式使用。

## 打包与发布

当前推荐用 PyInstaller 构建单文件 Windows exe：

```powershell
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name SteamAccountManager --icon imgs\gnuhl-7oo8y-001.ico --add-data "imgs\gnuhl-7oo8y-001.ico;imgs" --exclude-module tkinter --exclude-module legacy main.py
```

构建产物位于：

```text
dist/SteamAccountManager.exe
```

运行时数据路径已按打包场景处理：源码运行时写入项目目录的 `data/`，exe 运行时写入 exe 同目录的 `data/`。首次运行会自动创建 `data/accounts.json` 和 `data/settings.json`。发布时只需要提供 exe，不要把真实 `data/` 一起打包或提交。

## 当前数据结构

`SteamAccount` 主要字段：

- `account_id`
  本地唯一主键，UUID，用于界面选中、编辑、删除等内部操作
- `profile_name`
  显示名称
- `login_name`
  Steam 登录名。当前也被用作导入时的匹配字段
- `password`
  密码
- `email`
  邮箱
- `phone`
  电话或其他辅助字段
- `five_e_rank`
  5E 分段；空值会规范为 `未定级`，已定级值按 `S`、`A++`、`A+`、`A`、`B++`、`B+`、`B`、`C++`、`C+`、`C`、`D` 排序
- `status`
  内部状态 key，目前有 `active`、`pending`、`frozen`、`disabled`
- `last_login`
  最后登录时间文本
- `frozen_until`
  5E 平台冻结/封禁截止时间文本；界面会按本地时间计算大致剩余时间
- `note`
  备注
- `created_at`
  创建时间
- `updated_at`
  更新时间

## 已完成的重要改动

### 1. 界面布局调整

- 已切换为 PySide6 界面
- PySide6 界面会根据 Windows 应用主题自动使用亮色或暗色样式
- 主界面改为顶部工具栏 + 全宽账号表格 + 批量操作栏
- 新建/编辑账号使用独立弹窗
- 快速保存/文本导入使用独立弹窗
- Steam 登录、Steam 路径选择、退出方式和登录状态已整合到独立“Steam 登录与设置”弹窗

### 1.1 批量账号管理

- 左侧账号列表支持多选
- 支持批量删除选中的账号
- 支持批量修改选中账号的状态
- 多选时右侧详情仍显示第一个选中账号，登录和手动编辑仍按当前详情账号处理

### 2. 双语支持

- 已做中英文界面文案
- 根据系统语言自动切换
- 状态值已改成内部 key + 当前语言显示标签的模式
- 导入提示文案也支持双语

### 3. 保存失败保护

- 保存 `accounts.json` 或 `settings.json` 失败时，不会直接崩溃
- 会弹窗提示错误信息
- 对账号保存、删除、导入等操作增加了失败后的内存回滚

### 4. JSON 损坏提示

- `accounts.json` 或 `settings.json` 读取失败、解析失败或结构校验失败时，不再静默当成空数据
- `accounts.json` 根节点必须是列表，列表项必须是对象；`settings.json` 根节点必须是对象
- 会生成 `*.invalid-时间戳.json` 备份副本
- 程序继续启动，但会弹窗提示哪个文件损坏、备份位置在哪

### 5. 手动保存重复校验

- 手动保存账号时，如果 `login_name` 和其他账号重复，会阻止保存并提示
- 内部排除当前 `account_id`，不会把自己误判成重复

### 6. 导入流程更明确

- 导入前先预览
- 明确展示本次会新增多少、覆盖多少、跳过多少
- 明确提示“覆盖规则按 `login_name` 匹配已有账号”
- 如果导入文本内部自己就有重复 `login_name`，会在确认前提示，并说明按最后一条生效
- 额外提供“快速保存”入口，适合粘贴 `accounts.txt` 这类一行一个账号的文本；既支持单行直接保存，也支持多行一次导入多个账号
- 批量导入分块逻辑已增强：一行一个完整账号时按行导入；一个账号拆成多行时会按账号起始标记合并；单段黏连文本会按 `5E账号` 或 `steam账号` 等起始标记切分
- 覆盖已有账号时只用导入文本里解析到的非空字段更新，不再用空 `last_login` 或空备注清掉已有数据
- 手动填写账号详情的方式仍然保留

### 7. Steam 已运行时的处理

- 登录前会检测 `steam.exe` 或 `steamwebhelper.exe` 是否正在运行
- 如果 Steam 已运行，默认会先通过 `steam.exe -shutdown` 请求 Steam 正常退出
- 如果长时间未退出，会弹窗询问是否使用 `taskkill /T /F` 强制结束相关进程
- 界面中提供“Steam 退出方式”设置，可选择“温和退出，超时后询问”或“直接强制结束”
- 确认 Steam 相关进程退出后，再用目标账号重新启动 Steam

## 当前登录功能现状

当前“登录 Steam”按钮流程大致如下：

1. 获取当前表单里的 `login_name` 和 `password`
2. 尝试找到或选择 `steam.exe`
3. 如果检测到 `steam.exe` 或 `steamwebhelper.exe` 正在运行，按界面中的“Steam 退出方式”设置处理
4. 使用 `steam.exe -login <login_name> <password>` 启动 Steam
5. 将登录流程状态回写到界面

当前状态说明：

- 登录流程不再依赖聚焦窗口、剪贴板粘贴和模拟按键
- 稳定性主要取决于 Steam 是否接受 `-login` 参数、Steam Guard、网络状态、客户端弹窗等外部因素
- 如果 Steam Guard 或其他安全验证出现，仍需要用户手动完成
- `system_utils.py` 中仍保留了窗口枚举、剪贴板和原生控件填充相关函数，后续如果要做 UI Automation 或兼容备用登录方案，可以继续复用

## 关于安全策略

当前项目是本地单机使用、批量存储小号的工具，因此账号密码仍然保存在本地 JSON 中，没有做加密存储。这是当前使用场景下接受的取舍。

## 已讨论但尚未实现的方向

### 1. 更稳的自动化登录

已经讨论过：

- 旧的键盘模拟方式不够稳
- 当前主流程已经改为 `steam.exe -login`，避免了大部分焦点和输入问题
- 如果后续继续做“全自动”，可以调研 UI Automation 作为备用或增强方案
- 是否可行，取决于 Steam 登录界面是原生控件还是嵌入式 webview
- 已为此准备了 `steam_ui_probe.py`

### 2. 登录流程可观测性与错误处理

后续可以继续完善：

- 区分“Steam 启动成功”和“账号实际登录成功”
- 对 `taskkill` 失败、Steam 启动失败、Steam Guard 等场景给出更明确提示
- 记录最近一次登录尝试时间或结果，更新 `last_login`
- 根据需要增加“是否先关闭已运行 Steam”的确认选项，当前已提供退出策略设置但还没有每次弹窗确认

## 当前结论

这个项目现在已经是一个可用的本地 Steam 账号管理工具，结构清楚，基础功能完整，错误处理也比最初完善了不少。

如果下一次开启新对话，优先可以从下面两个方向里选一个继续：

- 完善登录结果判断、错误提示和 `last_login` 更新
- 调查 Steam 登录界面结构，决定后续是否需要 UI Automation 备用方案

## 额外背景

- 这个项目最初目录名叫 `something`
- 现在已经改名为 `steam_account_manager`
- 旧目录已经删除
