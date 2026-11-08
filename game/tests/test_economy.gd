extends GutTest
## 产出公式、消耗与加成计算的单元测试。

var gs: Node


func before_each() -> void:
	gs = StateFactory.make_state(self)


func after_each() -> void:
	gs.free()


func test_base_production_without_upgrades() -> void:
	var base_jade := float(GameData.config["base_production"]["jade"])
	var base_fuel := float(GameData.config["base_production"]["fuel"])
	assert_almost_eq(Economy.production_rate(gs, "jade"), base_jade, 0.0001)
	assert_almost_eq(Economy.production_rate(gs, "fuel"), base_fuel, 0.0001)
	assert_eq(Economy.production_rate(gs, "material"), 0.0, "素材没有自动产出")


func test_car_level_coefficient() -> void:
	# 客车厢 +10%/级：3 级 → ×1.3
	gs.car_levels["passenger"] = 3
	var base_jade := float(GameData.config["base_production"]["jade"])
	assert_almost_eq(Economy.production_rate(gs, "jade"), base_jade * 1.3, 0.0001)
	# 客车厢不影响燃料
	var base_fuel := float(GameData.config["base_production"]["fuel"])
	assert_almost_eq(Economy.production_rate(gs, "fuel"), base_fuel, 0.0001)


func test_character_bonus_sum() -> void:
	# 丹恒 +15% 星琼
	gs.characters["danheng"] = 1
	var base_jade := float(GameData.config["base_production"]["jade"])
	assert_almost_eq(Economy.production_rate(gs, "jade"), base_jade * 1.15, 0.0001)
	# 姬子 +15% 燃料，不影响星琼
	gs.characters["himeko"] = 1
	var base_fuel := float(GameData.config["base_production"]["fuel"])
	assert_almost_eq(Economy.production_rate(gs, "fuel"), base_fuel * 1.15, 0.0001)
	assert_almost_eq(Economy.production_rate(gs, "jade"), base_jade * 1.15, 0.0001)


func test_full_formula_car_times_character() -> void:
	# 每秒产出 = 基础值 × 车厢等级系数 × (1 + 角色加成总和)
	gs.car_levels["power"] = 5          # ×1.5
	gs.characters["himeko"] = 3         # 15% + 5% × 2 = 25%
	var base_fuel := float(GameData.config["base_production"]["fuel"])
	assert_almost_eq(Economy.production_rate(gs, "fuel"), base_fuel * 1.5 * 1.25, 0.0001)


func test_passive_scales_with_level() -> void:
	var def := GameData.get_character("danheng")
	assert_almost_eq(Economy.passive_value(def, 1), 0.15, 0.0001)
	assert_almost_eq(Economy.passive_value(def, 2), 0.20, 0.0001)
	assert_almost_eq(Economy.passive_value(def, 0), 0.15, 0.0001, "0 级按 1 级处理")


func test_upgrade_cost_geometric_growth() -> void:
	var def := GameData.get_car("power")
	var base := float(def["base_cost"])
	var growth := float(def["cost_growth"])
	assert_eq(Economy.upgrade_cost("power", 0), floorf(base))
	assert_eq(Economy.upgrade_cost("power", 1), floorf(base * growth))
	assert_eq(Economy.upgrade_cost("power", 10), floorf(base * pow(growth, 10)))
	assert_true(Economy.upgrade_cost("power", 11) > Economy.upgrade_cost("power", 10))


func test_unknown_car_cost_is_infinite() -> void:
	assert_true(is_inf(Economy.upgrade_cost("not_a_car", 0)))


func test_offline_cap_bonuses() -> void:
	var base := float(GameData.config["offline"]["base_cap_seconds"])
	assert_almost_eq(Economy.offline_cap_seconds(gs), base, 0.001)
	gs.car_levels["cargo"] = 2          # +30 分钟/级
	assert_almost_eq(Economy.offline_cap_seconds(gs), base + 3600.0, 0.001)
	gs.characters["welt"] = 1           # +2 小时
	assert_almost_eq(Economy.offline_cap_seconds(gs), base + 3600.0 + 7200.0, 0.001)


func test_travel_speed_bonus() -> void:
	var base := float(GameData.config["travel"]["base_seconds"])
	assert_almost_eq(Economy.travel_seconds(gs), base, 0.001)
	gs.characters["march7"] = 1         # +15% 速度
	assert_almost_eq(Economy.travel_seconds(gs), base / 1.15, 0.001)


func test_dispatch_reward_with_cargo_car() -> void:
	var short := GameData.get_duration("short")
	var base := float(short["material"])
	assert_eq(Economy.dispatch_reward(gs, "short"), floorf(base))
	gs.car_levels["cargo"] = 3          # +30%
	assert_eq(Economy.dispatch_reward(gs, "short"), floorf(base * 1.3))


func test_dispatch_slots_by_planet() -> void:
	gs.planet_index = 0
	assert_eq(Economy.dispatch_slots(gs), 1)
	gs.planet_index = 1
	assert_eq(Economy.dispatch_slots(gs), 1)
	gs.planet_index = 2
	assert_eq(Economy.dispatch_slots(gs), 2)


func test_unlocks_follow_planets() -> void:
	gs.planet_index = 0
	assert_true(Economy.is_car_unlocked(gs, "power"))
	assert_false(Economy.is_car_unlocked(gs, "cargo"))
	assert_true(Economy.is_character_unlocked(gs, "march7"))
	assert_false(Economy.is_character_unlocked(gs, "himeko"))
	assert_false(Economy.is_character_unlocked(gs, "welt"))
	gs.planet_index = 1
	assert_true(Economy.is_car_unlocked(gs, "cargo"))
	assert_true(Economy.is_character_unlocked(gs, "himeko"))
	gs.planet_index = 2
	assert_true(Economy.is_character_unlocked(gs, "welt"))


func test_next_planet_fuel_cost() -> void:
	gs.planet_index = 0
	assert_eq(Economy.next_planet_fuel_cost(gs), 500.0)
	gs.planet_index = 1
	assert_eq(Economy.next_planet_fuel_cost(gs), 5000.0)
	gs.planet_index = 2
	assert_true(is_inf(Economy.next_planet_fuel_cost(gs)))


func test_number_format() -> void:
	assert_eq(NumberFormat.format(0.0), "0")
	assert_eq(NumberFormat.format(999.9), "999")
	assert_eq(NumberFormat.format(1234.0), "1.2K")
	assert_eq(NumberFormat.format(3400000.0), "3.4M")
	assert_eq(NumberFormat.format(5600000000.0), "5.6B")
	assert_eq(NumberFormat.format(1000.0), "1K")
	assert_eq(NumberFormat.format(-2500.0), "-2.5K")
	assert_eq(NumberFormat.format_duration(3725.0), "1小时2分5秒")
	assert_eq(NumberFormat.format_clock(65.0), "01:05")
	assert_eq(NumberFormat.format_percent(0.15), "+15%")
