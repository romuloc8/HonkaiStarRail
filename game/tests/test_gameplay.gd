extends GutTest
## 核心操作：升级、招募、派遣、启航、事件。

var gs: Node


func before_each() -> void:
	gs = StateFactory.make_state(self)


func after_each() -> void:
	gs.free()


func test_upgrade_car_spends_jade() -> void:
	assert_false(gs.upgrade_car("power"), "没钱不能升级")
	var cost := Economy.upgrade_cost("power", 0)
	gs.resources["jade"] = cost + 10.0
	assert_true(gs.upgrade_car("power"))
	assert_eq(gs.car_level("power"), 1)
	assert_almost_eq(gs.resources["jade"], 10.0, 0.0001)


func test_locked_car_cannot_upgrade() -> void:
	gs.resources["jade"] = 1e9
	assert_false(gs.upgrade_car("cargo"), "货运车厢在第二个星球解锁")
	gs.planet_index = 1
	assert_true(gs.upgrade_car("cargo"))


func test_recruit_and_upgrade_character() -> void:
	gs.resources["jade"] = 1e6
	assert_false(gs.recruit("welt"), "瓦尔特在第三个星球解锁")
	assert_true(gs.recruit("march7"))
	assert_false(gs.recruit("march7"), "不能重复招募")
	assert_eq(gs.character_level("march7"), 1)
	assert_false(gs.upgrade_character("march7"), "没有素材")
	gs.resources["material"] = Economy.character_upgrade_cost(1)
	assert_true(gs.upgrade_character("march7"))
	assert_eq(gs.character_level("march7"), 2)
	assert_eq(gs.resources["material"], 0.0)


func test_all_four_characters_recruitable_on_last_planet() -> void:
	gs.planet_index = 2
	gs.resources["jade"] = 1e6
	for def in GameData.characters:
		assert_true(gs.recruit(def["id"]), "可招募 %s" % def["name"])
	assert_eq(gs.characters.size(), 4)


func test_dispatch_flow() -> void:
	gs.characters["danheng"] = 1
	assert_false(gs.start_dispatch(0, "himeko", "short"), "未招募不能派遣")
	assert_false(gs.start_dispatch(5, "danheng", "short"), "槽位不存在")
	assert_false(gs.start_dispatch(0, "danheng", "forever"), "时长不存在")
	assert_true(gs.start_dispatch(0, "danheng", "short"))
	assert_true(gs.is_character_dispatched("danheng"))
	assert_false(gs.start_dispatch(0, "danheng", "short"), "槽位已占用")
	assert_eq(gs.collect_dispatch(0), 0.0, "未完成不能收取")
	gs.tick(600.0, false)
	assert_true(gs.is_dispatch_complete(0))
	var reward: float = gs.collect_dispatch(0)
	assert_eq(reward, Economy.dispatch_reward(gs, "short"))
	assert_eq(gs.resources["material"], reward)
	assert_true(gs.get_dispatch(0).is_empty())
	assert_false(gs.is_character_dispatched("danheng"))


func test_second_slot_unlocks_on_third_planet() -> void:
	assert_eq(gs.dispatches.size(), 1)
	gs.resources["fuel"] = 1e6
	gs.depart()
	gs.tick(1000.0, false)
	assert_eq(gs.planet_index, 1)
	assert_eq(gs.dispatches.size(), 1)
	gs.depart()
	gs.tick(1000.0, false)
	assert_eq(gs.planet_index, 2)
	assert_eq(gs.dispatches.size(), 2)


func test_depart_requires_fuel_and_travel_completes() -> void:
	assert_false(gs.depart())
	gs.resources["fuel"] = 500.0
	assert_true(gs.depart())
	assert_eq(gs.resources["fuel"], 0.0)
	assert_true(gs.is_traveling())
	assert_false(gs.depart(), "航行中不能再次启航")
	gs.tick(30.0, false)
	assert_almost_eq(gs.travel_progress(), 0.5, 0.01)
	gs.tick(30.0, false)
	assert_false(gs.is_traveling())
	assert_eq(gs.planet_index, 1)
	assert_eq(gs.current_planet()["id"], "jarilo_vi")


func test_cannot_depart_from_last_planet() -> void:
	gs.planet_index = 2
	gs.resources["fuel"] = 1e9
	assert_false(gs.has_next_planet())
	assert_false(gs.depart())


func test_event_resolution_applies_effects() -> void:
	gs.resources["jade"] = 1000.0
	gs.pending_events = ["pom_pom_audit"]
	var changes: Dictionary = gs.resolve_event(0)   # 星琼 +5%
	assert_almost_eq(changes["jade"], 50.0, 0.0001)
	assert_almost_eq(gs.resources["jade"], 1050.0, 0.0001)
	assert_eq(gs.pending_events.size(), 0)

	gs.pending_events = ["pom_pom_audit"]
	changes = gs.resolve_event(1)                   # 素材 +15
	assert_eq(changes["material"], 15.0)
	assert_eq(gs.resources["material"], 15.0)


func test_negative_effect_cannot_go_below_zero() -> void:
	gs.resources["fuel"] = 5.0
	var changes: Dictionary = gs.apply_effects([{"type": "fuel", "value": -20}])
	assert_eq(gs.resources["fuel"], 0.0)
	assert_eq(changes["fuel"], -5.0)


func test_at_least_ten_events_and_all_can_trigger() -> void:
	assert_true(GameData.events.size() >= 10, "原型至少 10 条事件")
	var seen := {}
	for i in range(GameData.events.size() * 3):
		var ev: Dictionary = gs.pick_event("online")
		if not ev.is_empty():
			seen[ev["id"]] = true
			gs.triggered_events.append(ev["id"])
	# 专属抵达事件只在对应星球触发，所以这里统计通用事件
	var generic_count := GameData.events.filter(func(e): return e.get("trigger", "any") == "any").size()
	assert_eq(seen.size(), generic_count)
	# 抵达事件
	gs.planet_index = 2
	var arrival: Dictionary = gs.pick_event("arrival")
	assert_eq(arrival["id"], "luofu_market")


func test_event_has_two_options_with_effects() -> void:
	for ev in GameData.events:
		assert_eq(ev["options"].size(), 2, "%s 应有两个选项" % ev["id"])
		for opt in ev["options"]:
			assert_true(opt["effects"].size() >= 1, "%s 的选项应有效果" % ev["id"])
			assert_true(gs.describe_effects(opt["effects"]).length() > 0)
