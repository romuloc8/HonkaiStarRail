"""
实体桥接器：建立 entities.json ↔ LightRAG 知识图谱节点之间的对应关系。

解决问题：entities.json 和 LightRAG 分别独立构建，同一实体可能有不同名称
（"可可利亚" vs "可可利亚·兰德" vs "守护者可可利亚"），无法互相查询。

运行：
    python3 -m starrail_rag.tools.entity_bridge

输出：
    output/entity_bridge.json
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_ROOT  = Path("/workspace")
OUTPUT_DIR = DATA_ROOT / "output"


def _normalize(name: str) -> str:
    """规范化实体名用于匹配（去标点、全角转半角、小写）。"""
    name = re.sub(r'[·•·\s「」『』【】《》〈〉（）()…—""'']', '', name)
    return name.lower()


def _edit_distance(a: str, b: str) -> int:
    """计算编辑距离（Levenshtein）。"""
    if len(a) > 50 or len(b) > 50:
        return 999
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i-1] == b[j-1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j-1])
            prev = temp
    return dp[n]


def load_entities_json(path: Path = OUTPUT_DIR / "entities.json") -> dict[str, dict]:
    """返回 canonical → entity 映射。"""
    data = json.load(open(path))
    return {e["canonical"]: e for e in data["entities"]}


def load_lightrag_entities(lightrag_dir: Path = OUTPUT_DIR / "lightrag_db") -> list[str]:
    """从 LightRAG 的 kv_store_full_entities.json 提取所有节点名称。"""
    path = lightrag_dir / "kv_store_full_entities.json"
    if not path.exists():
        logger.warning("LightRAG entities file not found: %s", path)
        return []

    data = json.load(open(path))
    # LightRAG stores entities as {id: {entity_name: ..., description: ...}}
    names = []
    for entity_data in data.values():
        if isinstance(entity_data, dict):
            name = entity_data.get("entity_name") or entity_data.get("name", "")
            if name:
                names.append(name)
    return names


def build_bridge(
    entities_path: Path  = OUTPUT_DIR / "entities.json",
    lightrag_dir: Path   = OUTPUT_DIR / "lightrag_db",
    output_path: Path    = OUTPUT_DIR / "entity_bridge.json",
    fuzzy_threshold: int = 2,
) -> dict[str, list[str]]:
    """
    构建 entities.json canonical → LightRAG 节点名称列表 的映射。

    匹配顺序：
    1. 精确匹配
    2. 规范化后精确匹配（去标点）
    3. 别称匹配
    4. 编辑距离 ≤ fuzzy_threshold 的模糊匹配
    """
    entities = load_entities_json(entities_path)
    lightrag_names = load_lightrag_entities(lightrag_dir)

    if not lightrag_names:
        logger.warning("LightRAG 节点为空，桥接表将为空")

    # 构建 LightRAG 名称的规范化索引
    lg_norm: dict[str, str] = {_normalize(n): n for n in lightrag_names}

    bridge: dict[str, dict] = {}
    unmatched = []

    for canonical, entity in entities.items():
        matches: list[tuple[str, str]] = []  # [(lightrag_name, match_method)]

        # 1. 精确匹配
        if canonical in lightrag_names:
            matches.append((canonical, "exact"))

        # 2. 规范化匹配
        norm_can = _normalize(canonical)
        if norm_can in lg_norm and lg_norm[norm_can] not in [m[0] for m in matches]:
            matches.append((lg_norm[norm_can], "normalized"))

        # 3. 别称匹配
        for alias in entity.get("aliases", []):
            if alias in lightrag_names and alias not in [m[0] for m in matches]:
                matches.append((alias, "alias"))
            norm_alias = _normalize(alias)
            if norm_alias in lg_norm and lg_norm[norm_alias] not in [m[0] for m in matches]:
                matches.append((lg_norm[norm_alias], "alias_normalized"))

        # 4. 模糊匹配（仅当无精确/别称匹配时）
        if not matches:
            for lg_name in lightrag_names:
                dist = _edit_distance(norm_can, _normalize(lg_name))
                if dist <= fuzzy_threshold:
                    matches.append((lg_name, f"fuzzy_d{dist}"))

        if matches:
            bridge[canonical] = {
                "lightrag_nodes":     [m[0] for m in matches],
                "primary_lightrag_id": matches[0][0],
                "match_methods":      [m[1] for m in matches],
                "best_confidence":    1.0 if matches[0][1] in ("exact", "alias") else 0.8,
            }
        else:
            unmatched.append(canonical)

    logger.info(
        "桥接完成：%d/%d 实体有对应 LightRAG 节点，%d 未匹配",
        len(bridge), len(entities), len(unmatched),
    )

    output = {
        "version": "1.0",
        "total_entities_json": len(entities),
        "total_lightrag_nodes": len(lightrag_names),
        "matched": len(bridge),
        "unmatched_count": len(unmatched),
        "bridge": bridge,
        "unmatched_entities": unmatched[:100],  # 只记录前100个
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(output, open(output_path, "w"), ensure_ascii=False, indent=2)
    logger.info("桥接表已保存到 %s", output_path)
    return bridge


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_bridge()
