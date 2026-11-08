extends Node
## 产出与数值计算。所有函数都是无副作用的“查询”，接收一个 state
## （GameState 实例或任何带有 car_levels / characters / planet_index 的对象），
## 便于单元测试。
##
## 产出公式：每秒产出 = 基础值 × 车厢等级系数 × (1 + 角色加成总和)
##   车厢等级系数 = 1 + Σ(车厢每级加成 × 等级)
##   角色加成总和 = Σ(已招募角色对应类型的被动数值)


# ---------------------------------------------------------------------------
# 加成汇总
# ---------------------------------------------------------------------------

## 所有车厢中 effect.type == effect_type 的加成之和（已乘等级）。
func car_bonus(state, effect_type: String) -> float:
	var total := 0.0
	for car in GameData.cars:
		var level := int(state.car_levels.get(car["id"], 0))
		if level <= 0:
			continue
		for effect in car.get("effects", []):
			if effect.get("type", "") == effect_type:
				total += float(effect.get("per_level", 0.0)) * level
	return total


## 所有已招募角色中 passive.type == passive_type 的被动之和（已考虑角色等级）。
func char_bonus(state, passive_type: String) -> float:
	var total := 0.0
	for char_id in state.characters.keys():
		var def: Dictionary = GameData.get_character(char_id)
		if def.is_empty():
			continue
		var passive: Dictionary = def.get("passive", {})
		if passive.get("type", "") == passive_type:
			total += passive_value(def, int(state.characters[char_id]))
	return total


## 角色被动在某等级下的数值：基础值 + 每级增量 × (等级 - 1)。
func passive_value(def: Dictionary, level: int) -> float:
	var passive: Dictionary = def.get("passive", {})
	var base := float(passive.get("value", 0.0))
	var per_level := float(passive.get("per_level", 0.0))
	return base + per_level * maxi(level - 1, 0)


# ---------------------------------------------------------------------------
# 产出
# ---------------------------------------------------------------------------

## 某资源的每秒自动产出。
func production_rate(state, resource: String) -> float:
	var base := float(GameData.config.get("base_production", {}).get(resource, 0.0))
	if base <= 0.0:
		return 0.0
	var car_coef := 1.0 + car_bonus(state, resource + "_production")
	var char_sum := char_bonus(state, resource + "_production")
	return base * car_coef * (1.0 + char_sum)


## 所有资源的每秒产出，{"jade": x, "fuel": y, "material": z}。
func production_rates(state) -> Dictionary:
	var out := {}
	for res in GameData.get_resources():
		var id: String = res["id"]
		out[id] = production_rate(state, id)
	return out


# ---------------------------------------------------------------------------
# 消耗
# ---------------------------------------------------------------------------

## 车厢从 current_level 升到下一级所需星琼（几何增长）。
func upgrade_cost(car_id: String, current_level: int) -> float:
	var def := GameData.get_car(car_id)
	if def.is_empty():
		return INF
	var base := float(def.get("base_cost", 0.0))
	var growth := float(def.get("cost_growth", 1.0))
	return floorf(base * pow(growth, current_level))


func recruit_cost(char_id: String) -> float:
	var def := GameData.get_character(char_id)
	if def.is_empty():
		return INF
	return float(def.get("recruit_cost", 0.0))


## 角色从 current_level 升到下一级所需素材。
func character_upgrade_cost(current_level: int) -> float:
	var cfg: Dictionary = GameData.config.get("character_upgrade", {})
	var base := float(cfg.get("base_material_cost", 10.0))
	var growth := float(cfg.get("cost_growth", 1.5))
	return floorf(base * pow(growth, maxi(current_level - 1, 0)))


func character_max_level() -> int:
	return int(GameData.config.get("character_upgrade", {}).get("max_level", 10))


# ---------------------------------------------------------------------------
# 离线 / 航行 / 派遣
# ---------------------------------------------------------------------------

## 离线收益上限（秒）：基础 8 小时 + 货运车厢 + 瓦尔特。
func offline_cap_seconds(state) -> float:
	var base := float(GameData.config.get("offline", {}).get("base_cap_seconds", 28800.0))
	return base + car_bonus(state, "offline_cap_seconds") + char_bonus(state, "offline_cap_seconds")


## 一次航行需要的秒数：基础 60 秒 ÷ (1 + 航行速度加成)。
func travel_seconds(state) -> float:
	var base := float(GameData.config.get("travel", {}).get("base_seconds", 60.0))
	var speed := 1.0 + car_bonus(state, "travel_speed") + char_bonus(state, "travel_speed")
	return base / maxf(speed, 0.01)


## 某档派遣任务完成后获得的素材。
func dispatch_reward(state, duration_id: String) -> float:
	var duration := GameData.get_duration(duration_id)
	if duration.is_empty():
		return 0.0
	var base := float(duration.get("material", 0.0))
	var mult := 1.0 + car_bonus(state, "dispatch_yield") + char_bonus(state, "dispatch_yield")
	return floorf(base * mult)


## 当前已解锁的派遣槽位数量（累加已抵达星球的 unlocks.dispatch_slots）。
func dispatch_slots(state) -> int:
	var total := 0
	var last := mini(int(state.planet_index), GameData.planets.size() - 1)
	for i in range(last + 1):
		total += int(GameData.planets[i].get("unlocks", {}).get("dispatch_slots", 0))
	return total


# ---------------------------------------------------------------------------
# 解锁
# ---------------------------------------------------------------------------

func is_car_unlocked(state, car_id: String) -> bool:
	var idx := GameData.unlock_planet_index("cars", car_id)
	return idx >= 0 and idx <= int(state.planet_index)


func is_character_unlocked(state, char_id: String) -> bool:
	var idx := GameData.unlock_planet_index("characters", char_id)
	return idx >= 0 and idx <= int(state.planet_index)


## 启航到下一个星球所需燃料；没有下一个星球返回 INF。
func next_planet_fuel_cost(state) -> float:
	var next := GameData.get_planet_at(int(state.planet_index) + 1)
	if next.is_empty():
		return INF
	return float(next.get("fuel_cost", 0.0))
