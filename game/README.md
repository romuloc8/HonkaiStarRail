# 《星穹列车·远航》原型

基于《崩坏：星穹铁道》世界观的同人放置小游戏原型（iOS 竖屏，Godot 4 + GDScript）。个人练习 / 朋友间分享用途，不商用，不含任何官方素材，角色与星球名称沿用原作。

需求文档见项目 PM 维护的《星穹列车·远航》原型需求文档 v0.1；本目录是该文档的实现。

## 玩法概览

- 星穹列车停靠在星球上自动产出 **星琼** 与 **燃料**，角色派遣任务产出 **素材**。
- 用星琼升级三节车厢（动力 / 客车 / 货运），用星琼招募 4 名角色（三月七、丹恒、姬子、瓦尔特），用素材给角色升级。
- 燃料攒够后「启航」前往下一个星球：空间站「黑塔」→ 雅利洛-Ⅵ → 仙舟「罗浮」，抵达后解锁新车厢 / 角色 / 派遣槽位，并触发一条文本事件（二选一）。
- 每累计 10 分钟在线也会触发一条事件；原型内置 10 条事件（`data/events.json`）。
- 离线期间按真实时间结算产出与派遣进度，上限 8 小时（货运车厢 +30 分钟/级，瓦尔特 +2 小时），重新打开时弹出「离线收益」。
- 存档保存在 `user://save.json`，带版本号；每 30 秒、关键操作后、应用切后台 / 关闭时自动保存。

## 环境要求

- **Godot 4.3 或更新的 4.x 稳定版**（标准版即可，无需 .NET）。
  本原型在 Godot **4.3-stable** 和 **4.7.2-stable** 上验证过：游戏可运行、全部单元测试通过。
- 渲染器：Mobile（项目已配置）。
- macOS 上预览、iPhone 真机运行需要 Xcode，见下文「导出 iOS」。

## 在 Godot 中打开

1. 启动 Godot，项目管理器 → **导入** → 选择本目录下的 `project.godot`。
2. 第一次打开编辑器会自动导入资源并生成 `.godot/` 缓存。
3. 按 **F5**（运行项目）即可游玩；桌面预览窗口为 450×974（9:19.5 竖屏），实际设计分辨率 1170×2532，拉伸模式 `canvas_items` / `expand`，iPad 等其他比例也能自适应。

### 快速通关（调试加速）

「设置」页有 **调试加速 ×50** 开关：开启后产出、航行、派遣倒计时、在线事件计时全部 ×50，几分钟内即可从黑塔空间站玩到仙舟「罗浮」。离线收益仍按真实时间结算。
模拟测试（`tests/test_playthrough.gd`）中，一个贪心策略在游戏时间约 1 小时 35 分钟抵达第三个星球，开加速后约 2 分钟真实时间。

### 存档位置

| 平台 | 路径 |
|---|---|
| macOS | `~/Library/Application Support/Godot/app_userdata/星穹列车·远航/save.json` |
| Linux | `~/.local/share/godot/app_userdata/星穹列车·远航/save.json` |
| Windows | `%APPDATA%\Godot\app_userdata\星穹列车·远航\save.json` |
| iOS | 应用沙盒 `Documents/`（Godot 自动处理） |

「设置」页提供「立即保存」和带二次确认的「重置存档」。

## 运行单元测试

测试框架为 [GUT 9.4.0](https://github.com/bitwes/Gut)，已随项目放在 `addons/gut/`（MIT 协议），无需额外安装。

### 命令行（Linux / macOS，无头）

```bash
# 首次需要先导入资源，脚本会自动处理
GODOT=/path/to/godot ./run_tests.sh
```

等价的手动命令：

```bash
godot --headless --path . --import
godot --headless --path . -s addons/gut/gut_cmdln.gd -gconfig=.gutconfig.json -gexit
```

只跑某个文件：追加 `-gselect=test_economy`。

> 注：首次 `--import` 时 Godot 会打印一些 GUT 编辑器插件相关的加载警告（class_name 尚未索引），再运行一次即可；不影响测试结果。在 Godot 4.7 上 GUT 9.4 会在启动时打印一条自身的非致命脚本错误，测试仍全部通过；如需消除，可将 `addons/gut/` 替换为与所用 Godot 版本匹配的 GUT 版本。

### 编辑器内

项目设置 → 插件 → 启用 **Gut**，底部面板出现 GUT，点击 **Run All**。

### 测试内容

| 文件 | 覆盖 |
|---|---|
| `tests/test_economy.gd` | 产出公式（基础值 × 车厢系数 × (1 + 角色加成)）、升级费用几何增长、离线上限、航行速度、派遣收益、解锁规则、大数格式化 |
| `tests/test_offline.gd` | 离线结算：按 `min(离线秒数, 上限)` 结算产出 / 派遣 / 航行，不触发在线事件，调试加速倍率 |
| `tests/test_save_load.gd` | 存档写入与版本号、读档往返、损坏存档容错、版本迁移、启动时离线结算、重置存档 |
| `tests/test_gameplay.gd` | 升级、招募、角色升级、派遣流程、启航与抵达、事件效果、10 条事件均可触发 |
| `tests/test_ui_smoke.gd` | 主场景加载、Tab 切换、资源栏格式、卡片按钮、事件 / 离线 / 派遣弹窗、触控尺寸 |
| `tests/test_playthrough.gd` | 贪心玩家从头玩到第三个星球的整体模拟与数值平衡 |

GUT 命令行运行时 `GameState` 不会读写真实存档（检测到 `-g*` 参数即进入测试模式），测试使用 `user://test_save.json` 等临时文件并在结束后删除。

## 目录结构

```
game/
├── project.godot            # 项目配置：Mobile 渲染器、竖屏、1170×2532、canvas_items
├── autoload/
│   ├── GameData.gd          # 读取 data/*.json
│   ├── Economy.gd           # 产出 / 消耗 / 加成计算（纯查询函数）
│   └── GameState.gd         # 全局状态、tick、离线结算、事件、存档
├── data/
│   ├── config.json          # 基础产出、离线上限、航行时长、派遣档位、调试倍率等
│   ├── cars.json            # 三节车厢
│   ├── characters.json      # 四名角色
│   ├── planets.json         # 三个星球与解锁内容
│   └── events.json          # 10 条文本事件
├── scenes/
│   ├── main/                # Main.tscn：资源栏 + 四页切换 + 底部 Tab + 弹窗层；StarField 背景
│   ├── train/               # 列车页
│   ├── characters/          # 角色页（招募 / 升级 / 派遣）
│   ├── starmap/             # 星图页
│   ├── settings/            # 设置页
│   ├── popups/              # 通用弹窗 Modal（离线收益、事件、确认、派遣选择共用）
│   └── components/          # 代码构建的卡片：CarCard、CharacterCard、DispatchSlot、TrainView
├── scripts/
│   ├── NumberFormat.gd      # 1.2K / 3.4M / 5.6B、时长格式化
│   └── UIKit.gd             # 占位 UI 构建工具（按钮最小高度 44pt）
├── theme/main_theme.tres    # 深蓝 / 金色主题，系统字体回退（PingFang SC / Noto Sans CJK 等）
├── tests/                   # GUT 测试
├── addons/gut/              # GUT 测试框架
├── run_tests.sh             # 无头跑测试
└── icon.svg                 # 占位图标
```

### 调数值

所有数值都在 `data/*.json`：

- `config.json`：`base_production`（每秒基础产出）、`offline.base_cap_seconds`、`travel.base_seconds`、`events.online_interval_seconds`、`dispatch.durations`、`character_upgrade`、`debug.speed_multiplier`、`autosave_interval_seconds`。
- `cars.json`：`base_cost`、`cost_growth`（×1.15/级）、`effects[]`（`fuel_production` / `jade_production` / `dispatch_yield` / `offline_cap_seconds` 的每级加成）。
- `characters.json`：`recruit_cost`、`passive`（`type` / `value` / `per_level`）。角色每升一级被动 **加** `per_level`（百分比类 +5 个百分点，瓦尔特 +10 分钟）。
- `planets.json`：`fuel_cost`（启航到该星球所需燃料）、`unlocks`（车厢、角色、派遣槽位数）。
- `events.json`：`trigger` 为 `any`（在线 / 抵达都可）或 `arrival` + `planet`（指定星球专属）；`options[].effects[]` 支持 `jade_percent`、`jade`、`fuel`、`material`。

### 存档格式

```json
{
  "version": 1,
  "saved_at": 1731000000,
  "resources": {"jade": 0, "fuel": 0, "material": 0},
  "car_levels": {"power": 0, "passenger": 0, "cargo": 0},
  "characters": {"march7": 1},
  "dispatches": [{"char_id": "march7", "duration_id": "short", "total": 600, "remaining": 120, "reward": 10}],
  "planet_index": 0,
  "travel": {"active": false, "elapsed": 0, "target": 0},
  "triggered_events": [], "pending_events": [],
  "online_seconds": 0,
  "settings": {"sound": true, "debug_speed": false},
  "stats": {"total_online_seconds": 0, "total_offline_seconds": 0, "departures": 0}
}
```

升级存档结构时：`GameState.SAVE_VERSION` +1，并在 `GameState.migrate()` 的 `match` 中添加对应分支。

## 导出 iOS

iOS 导出只能在 **macOS** 上完成（Linux / Windows 无法生成 Xcode 工程）。

### 准备

1. 一台 Mac，安装最新 **Xcode**（含 iOS SDK 与命令行工具：`xcode-select --install`）。
2. **Apple 开发者账号**：免费 Apple ID 即可真机调试（每次签名 7 天有效，最多 3 台设备）；上架或 TestFlight 需要付费账号。
3. 在 Godot 中安装导出模板：**编辑器 → 管理导出模板 → 下载并安装**（版本需与编辑器完全一致）。

### 添加 iOS 预设

1. **项目 → 导出 → 添加… → iOS**。
2. 在预设中填写：
   - **Application → Bundle Identifier**：例如 `com.example.startrain`（需唯一）。
   - **Application → Team ID**：在 [developer.apple.com](https://developer.apple.com/account) → Membership 中查看；或先导出再在 Xcode 的 Signing 面板中选择 Team。
   - **Application → Short Version / Version**：`0.1.0` / `1`。
   - **Application → Min iOS Version**：建议 `14.0`+。
   - **Application → Targeted Device Family**：iPhone & iPad。
   - **Orientation**（项目设置里已锁定 `portrait`）；如需同时允许倒置竖屏，在项目设置 `display/window/handheld/orientation` 改为 `sensor_portrait`。
   - **Icons**：原型阶段可留空或指向 `icon.svg` 转出的 1024×1024 PNG；Godot 会自动生成各尺寸占位图。
   - **Launch Screen**：留默认或填一张纯色图。
3. 导出 → 选择目录（建议 `game/export/ios/`，已在 `.gitignore` 中忽略）→ 得到 `<项目名>.xcodeproj`。

### 在 Xcode 中签名并运行

1. 用 Xcode 打开导出的 `.xcodeproj`。
2. 选中 Target → **Signing & Capabilities** → 勾选 *Automatically manage signing* → 选择你的 Team。
3. 用数据线连接 iPhone，设备上开启 **开发者模式**（设置 → 隐私与安全性 → 开发者模式）。
4. 顶部选择该设备 → **Run (⌘R)**。首次运行需在手机 **设置 → 通用 → VPN 与设备管理** 中信任开发者证书。
5. 之后每次在 Godot 中修改代码，只需重新导出覆盖同一目录（Godot 会保留 Xcode 的签名设置），再 ⌘R。

### 常见问题

- **"Could not find template"**：导出模板版本与编辑器不一致，重新下载对应版本。
- **真机安装失败 / 签名错误**：检查 Bundle ID 是否唯一、Team 是否选对；免费账号需在 Xcode 中先登录 Apple ID（Settings → Accounts）。
- **中文显示为方块**：主题使用 `SystemFont`，iOS 上会自动回退到苹方；若想完全可控可在 `theme/main_theme.tres` 中替换为嵌入的开源 CJK 字体（如 Noto Sans SC）。
- **音频报错**：原型没有音频资源，设置页的音效开关只是静音主总线，留给后续接音效。

## 本次未实现（按需求文档第 9 节）

战斗、抽卡、多人、云存档、内购、音乐音效（仅预留开关）、正式美术、本地推送。

## 许可

同人练习项目，不商用。GUT 测试框架版权归 Tom "Butch" Wesley 所有（MIT，见 `addons/gut/LICENSE.md`）。
