"""
领域词表构建器 (W06)。

从游戏数据半自动提取核心实体，输出结构化 JSON 词表。
词表用于后续 LightRAG 建图时的 entity extraction prompt 注入，
以及向量检索时的同义词扩展。

实体类型:
  aeon      — 星神（含别称）
  path      — 命途
  character — 可玩角色
  faction   — 阵营/组织
  concept   — 重要概念（星核、开拓、虚数等）

运行:
  python -m starrail_rag.tools.domain_lexicon

输出:
  output/domain_lexicon.json
"""

from __future__ import annotations

import ctypes
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_ROOT = Path("/workspace")
OUTPUT_PATH = DATA_ROOT / "output" / "domain_lexicon.json"

# -----------------------------------------------------------------------
# 手工整理的别称表（游戏数据里无法自动关联的隐喻/雅称）
# 格式: canonical_name → [alias, ...]
# 后续 DeepSeek 步骤会扩充这里
# -----------------------------------------------------------------------
MANUAL_ALIASES: dict[str, list[str]] = {
    # 星神别称
    "岚（巡猎星神）": ["帝弓司命", "彼岸弓手", "巡猎", "猎星者"],
    "纳努克（毁灭星神）": ["灾厄", "毁灭", "无终的灾厄", "毁灭之神"],
    "博识尊（智识星神）": ["智识", "全知者", "Nous", "智慧之神"],
    "Ⅸ（虚无星神）": ["虚无", "乌有", "空洞", "虚无星神", "乌有女王"],
    "阿哈（欢愉星神）": ["大欢喜", "欢愉", "嬉笑者", "Aha", "那伟大的笑声"],
    "希佩（同谐星神）": ["钟表匠", "同谐", "时间仲裁者", "Xipe"],
    "克里珀（存护星神）": ["存护", "护盾之神", "Qlipoth", "筑城者"],
    "药师（丰饶星神）": ["丰饶", "母神", "繁衍之神"],
    "太一（秩序星神）": ["秩序", "Tayzzyronth", "繁育星神"],  # 注：太一=繁育，非秩序
    "浮黎（记忆星神）": ["记忆", "记忆守护者"],
    # 开拓星神（玩家命途）
    "阿基维利（开拓星神）": ["开拓", "先行者", "开拓之神", "Akivili"],
    # 主要角色的常用别称
    "开拓者": ["{NICKNAME}", "无名客", "旅行者"],
    "艾利欧": ["命运的奴隶", "Elio", "永恒的卡里乌斯"],
    "黄泉": ["死神小姐", "引路人"],
    # 重要组织/概念别称
    "星核猎手": ["猎手", "Stellaron Hunters"],
    "星际和平公司": ["银河公司", "IPC", "公司"],
    "天才俱乐部": ["智识博识尊的令使", "俱乐部成员"],
    "裂界": ["裂缝", "侵蚀", "虚数侵蚀"],
    "星核": ["万界之癌", "Stellaron", "星核病毒"],
    "反物质军团": ["虚卒", "末日兽", "反物质"],
}

# -----------------------------------------------------------------------
# 路径图标 → 命途英文代号映射
# -----------------------------------------------------------------------
_ICON_TO_PATH_EN = {
    "Knight": "Knight", "Memory": "Memory", "Warrior": "Warrior",
    "Rogue": "Rogue", "Mage": "Mage", "Shaman": "Shaman",
    "Warlock": "Warlock", "Priest": "Priest", "Elation": "Elation",
}


def _resolve(hash_val: int | None, textmap: dict[str, str]) -> str:
    if not hash_val:
        return ""
    key = str(hash_val)
    if key in textmap:
        return textmap[key]
    signed = ctypes.c_int64(hash_val).value
    return textmap.get(str(signed), "")


def _resolve_field(field: dict | str | None, textmap: dict[str, str]) -> str:
    if field is None:
        return ""
    if isinstance(field, dict):
        return _resolve(field.get("Hash"), textmap)
    return ""


def build_lexicon(data_root: Path = DATA_ROOT) -> dict:
    """
    构建领域词表，返回结构化字典。
    """
    with open(data_root / "TextMap" / "TextMapCHS.json", encoding="utf-8") as f:
        textmap = json.load(f)

    entities: list[dict] = []

    # ------------------------------------------------------------------
    # 1. 命途（Paths）— 来自 AvatarBaseType.json
    # ------------------------------------------------------------------
    with open(data_root / "ExcelOutput" / "AvatarBaseType.json", encoding="utf-8") as f:
        base_types = json.load(f)

    path_en_to_zh: dict[str, str] = {}
    for bt in base_types:
        path_en = bt.get("ID", "")
        path_zh = _resolve_field(bt.get("BaseTypeText"), textmap)
        if not path_zh:
            continue
        path_en_to_zh[path_en] = path_zh
        entities.append({
            "id": f"path_{path_en.lower()}",
            "type": "path",
            "canonical_name": path_zh,
            "aliases": [path_en],  # 英文代号作为别称
            "metadata": {"path_en": path_en},
        })

    logger.info("Extracted %d paths", len(path_en_to_zh))

    # ------------------------------------------------------------------
    # 2. 星神（Aeons）— 来自 RogueAeonDisplay.json
    # ------------------------------------------------------------------
    with open(data_root / "ExcelOutput" / "RogueAeonDisplay.json", encoding="utf-8") as f:
        aeon_display = json.load(f)

    for ad in aeon_display:
        aeon_name = _resolve_field(ad.get("RogueAeonName"), textmap)
        path_name1 = _resolve_field(ad.get("RogueAeonPathName"), textmap)  # e.g. "存护星神"
        path_name2 = _resolve_field(ad.get("RogueAeonPathName2"), textmap)  # e.g. "存护"

        if not aeon_name:
            continue

        # 推断命途：优先用图标路径，回落到 PathName2
        icon_path = ad.get("AeonIcon", "")
        path_en = next((k for k in _ICON_TO_PATH_EN if k in icon_path), "")
        path_zh = path_en_to_zh.get(path_en, "") if path_en else ""
        # 「通用」是兜底占位值，不是真实命途名，用 PathName2 替代
        if not path_zh or path_zh == "通用":
            path_zh = path_name2 or path_name1.replace("星神", "").strip()
        canonical = f"{aeon_name}（{path_zh}星神）" if path_zh else aeon_name
        aliases = []
        if path_name1 and path_name1 != canonical:
            aliases.append(path_name1)
        if path_name2 and path_name2 not in aliases and path_name2 != canonical:
            aliases.append(path_name2)

        # 追加手工别称
        for canon_key, manual_list in MANUAL_ALIASES.items():
            if aeon_name in canon_key or (path_zh and path_zh in canon_key):
                for alias in manual_list:
                    if alias not in aliases:
                        aliases.append(alias)

        entities.append({
            "id": f"aeon_{ad['DisplayID']}",
            "type": "aeon",
            "canonical_name": canonical,
            "aliases": aliases,
            "metadata": {
                "aeon_name": aeon_name,
                "path": path_zh,
                "path_en": path_en,
            },
        })

    logger.info("Extracted %d aeons", sum(1 for e in entities if e["type"] == "aeon"))

    # ------------------------------------------------------------------
    # 3. 可玩角色（Characters）— 来自 AvatarConfig.json
    # ------------------------------------------------------------------
    with open(data_root / "ExcelOutput" / "AvatarConfig.json", encoding="utf-8") as f:
        avatars = json.load(f)

    for av in avatars:
        if not av.get("Release"):
            continue
        name = _resolve_field(av.get("AvatarName"), textmap)
        full_name = _resolve_field(av.get("AvatarFullName"), textmap)
        if not name:
            continue

        aliases = []
        if full_name and full_name != name:
            aliases.append(full_name)

        # 追加手工别称
        for canon_key, manual_list in MANUAL_ALIASES.items():
            if name == canon_key or name in canon_key:
                for alias in manual_list:
                    if alias not in aliases:
                        aliases.append(alias)

        path_en = av.get("AvatarBaseType", "")
        entities.append({
            "id": f"character_{av['AvatarID']}",
            "type": "character",
            "canonical_name": name,
            "aliases": aliases,
            "metadata": {
                "avatar_id": av["AvatarID"],
                "path": path_en_to_zh.get(path_en, path_en),
                "element": av.get("DamageType", ""),
                "rarity": av.get("Rarity", ""),
            },
        })

    logger.info(
        "Extracted %d characters", sum(1 for e in entities if e["type"] == "character")
    )

    # ------------------------------------------------------------------
    # 4. 组织/阵营（Factions）— 手工整理 + 自动关联
    # ------------------------------------------------------------------
    factions = [
        {
            "id": "faction_stellaron_hunters",
            "type": "faction",
            "canonical_name": "星核猎手",
            "aliases": ["猎手", "Stellaron Hunters", "星核猎人"],
            "metadata": {},
        },
        {
            "id": "faction_ipc",
            "type": "faction",
            "canonical_name": "星际和平公司",
            "aliases": ["银河公司", "IPC", "公司", "和平公司"],
            "metadata": {},
        },
        {
            "id": "faction_genius_society",
            "type": "faction",
            "canonical_name": "天才俱乐部",
            "aliases": ["博识尊的令使", "智识的令使", "俱乐部"],
            "metadata": {},
        },
        {
            "id": "faction_cloud_knights",
            "type": "faction",
            "canonical_name": "云骑军",
            "aliases": ["仙舟云骑", "罗浮云骑"],
            "metadata": {},
        },
        {
            "id": "faction_underworld",
            "type": "faction",
            "canonical_name": "地火",
            "aliases": ["地下组织", "下层区抵抗力量"],
            "metadata": {},
        },
        {
            "id": "faction_express",
            "type": "faction",
            "canonical_name": "星穹列车",
            "aliases": ["列车组", "开拓者列车", "星穹快车"],
            "metadata": {},
        },
        {
            "id": "faction_silver_wolf",
            "type": "faction",
            "canonical_name": "银鬃铁卫",
            "aliases": ["铁卫", "贝洛伯格守卫"],
            "metadata": {},
        },
    ]
    entities.extend(factions)

    # ------------------------------------------------------------------
    # 5. 重要概念（Concepts）
    # ------------------------------------------------------------------
    concepts = [
        {
            "id": "concept_stellaron",
            "type": "concept",
            "canonical_name": "星核",
            "aliases": ["万界之癌", "Stellaron", "星核病毒", "灾星"],
            "metadata": {},
        },
        {
            "id": "concept_fragmentum",
            "type": "concept",
            "canonical_name": "裂界",
            "aliases": ["裂缝", "虚数侵蚀", "裂界生物", "裂隙"],
            "metadata": {},
        },
        {
            "id": "concept_trailblaze",
            "type": "concept",
            "canonical_name": "开拓",
            "aliases": ["开拓之道", "星际开拓"],
            "metadata": {},
        },
        {
            "id": "concept_imaginary",
            "type": "concept",
            "canonical_name": "虚数",
            "aliases": ["虚数之力", "虚数空间"],
            "metadata": {},
        },
    ]
    entities.extend(concepts)

    # ------------------------------------------------------------------
    # 添加纯手工别称条目（不属于上述分类的）
    # ------------------------------------------------------------------
    standalone_aliases = {
        "开拓者": ["无名客", "旅行者", "the Trailblazer"],
        "艾利欧": ["命运的奴隶", "Elio", "永恒的卡里乌斯", "剧本作者"],
    }
    for canon, aliases in standalone_aliases.items():
        entities.append({
            "id": f"manual_{canon}",
            "type": "character",
            "canonical_name": canon,
            "aliases": aliases,
            "metadata": {"source": "manual"},
        })

    lexicon = {
        "version": "1.0",
        "description": "崩坏：星穹铁道领域词表——星神、命途、角色、阵营、概念实体及别称",
        "stats": {
            "total_entities": len(entities),
            "by_type": {
                t: sum(1 for e in entities if e["type"] == t)
                for t in ["aeon", "path", "character", "faction", "concept"]
            },
        },
        "entities": entities,
    }

    return lexicon


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    lexicon = build_lexicon()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(lexicon, f, ensure_ascii=False, indent=2)

    print(f"\n词表已写入: {OUTPUT_PATH}")
    print(f"实体总数: {lexicon['stats']['total_entities']}")
    for t, n in lexicon["stats"]["by_type"].items():
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()
