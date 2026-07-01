# 星穹铁道数据看板

基于游戏原始数据（`ExcelOutput/`、`TextMap/`）构建的纯静态交互式 HTML 看板，**无需服务器、无需网络，浏览器直接打开即用**。

## 功能模块

| 模块 | 内容 |
|------|------|
| **总览** | 角色/遗器/光锥/成就数量统计 + 命途/属性分布可视化 |
| **角色百科** | 89 名角色卡片，支持按命途/属性/稀有度筛选，点击查看技能描述与星魂效果 |
| **遗器套装** | 56 套遗器（含位面饰品），展示 2/4 件套效果与属性加成 |
| **光锥图鉴** | 161 把光锥，按命途和稀有度筛选，点击查看技能效果 |
| **怪物弱点** | 441 种怪物弱点速查表，支持按元素筛选和名称搜索 |
| **成就** | 全部 1,781 个成就，按系列分组，支持全文搜索 |

## 快速开始

```bash
# 1. 安装依赖（仅需 Python 标准库，无额外依赖）
python3 --version   # 需要 Python 3.8+

# 2. 生成看板（在 hsr_dashboard/ 目录内执行）
cd hsr_dashboard
python3 build.py

# 3. 打开生成的 HTML 文件
open index.html        # macOS
xdg-open index.html    # Linux
start index.html       # Windows
```

## 参数说明

```
python3 build.py [选项]

  --data-root PATH   游戏数据根目录（默认: .. 即上级目录）
  --output    FILE   输出 HTML 文件路径（默认: index.html）
  --lang      CODE   TextMap 语言代码（默认: CHS）
                     可选: CHS / CHT / EN / JP / KR / DE / FR / ES / PT / RU / TH / VI / ID
```

## 多语言示例

```bash
# 英文版
python3 build.py --lang EN --output index_en.html

# 日文版
python3 build.py --lang JP --output index_jp.html
```

## 数据说明

| 文件 | 条目数 | 说明 |
|------|--------|------|
| `ExcelOutput/AvatarConfig.json` | 89 | 角色基础信息 |
| `ExcelOutput/AvatarSkillConfig.json` | 6,590 | 技能数据 |
| `ExcelOutput/AvatarRankConfig.json` | 594 | 星魂效果 |
| `ExcelOutput/AvatarPromotionConfig.json` | 623 | 突破属性参数 |
| `ExcelOutput/RelicSetConfig.json` | 56 | 遗器套装 |
| `ExcelOutput/EquipmentConfig.json` | 161 | 光锥 |
| `ExcelOutput/MonsterConfig.json` | 2,486 | 怪物（含弱点信息） |
| `ExcelOutput/AchievementData.json` | 1,781 | 成就 |
| `TextMap/TextMap*.json` | ~430,000 | 多语言文本（hash → 文本） |

> **属性说明**：角色属性页显示的 HP/攻击/防御为「满突破阶段」的基础值与每级成长值，速度/暴击为固定值。完整属性计算需要额外的等级倍率表（本数据集未包含）。

## 可扩展方向

1. **伤害计算器** — 结合技能倍率 `ParamList` 和属性值，计算理论输出
2. **组队协同分析** — 根据命途、属性、技能标签推荐最优组合
3. **养成路线规划** — 从 `ItemConfig` + `AvatarPromotionConfig` 提取突破/技能升级材料需求
4. **故事剧情浏览器** — 解析 `Story/Mission/` 中的对话序列，还原剧情文本
5. **副本怪物图鉴** — 关联 `StageConfig`（28,175 个关卡）与怪物弱点，生成攻略指南
6. **成就追踪工具** — 接入本地存档数据，实时同步完成进度

## 项目结构

```
hsr_dashboard/
├── build.py      # 数据处理 + HTML 生成脚本
├── index.html    # 生成的静态看板（运行 build.py 后出现）
└── README.md     # 本文档
```
