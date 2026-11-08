extends GutTest
## 整体流程模拟：一个简单的“贪心玩家”从黑塔空间站玩到仙舟「罗浮」。
## 同时验证数值平衡：在调试加速 ×50 下，几分钟真实时间即可走完原型流程。

var gs: Node


func before_each() -> void:
	gs = StateFactory.make_state(self)


func after_each() -> void:
	gs.free()


func _greedy_step() -> void:
	# 招募所有买得起的角色
	for def in GameData.characters:
		if gs.can_recruit(def["id"]):
			gs.recruit(def["id"])
	# 优先升级动力车厢（燃料是进度瓶颈），其次客车厢，再货运车厢
	for car_id in ["power", "passenger", "cargo"]:
		while gs.can_upgrade_car(car_id) and gs.car_level(car_id) < 40:
			gs.upgrade_car(car_id)
	# 有空槽就派遣，完成就收取
	for slot in gs.dispatch_slot_count():
		if gs.is_dispatch_complete(slot):
			gs.collect_dispatch(slot)
		if gs.get_dispatch(slot).is_empty():
			var idle: Array = gs.idle_characters()
			if not idle.is_empty():
				gs.start_dispatch(slot, idle[0], "short")
	# 事件全选第一项
	while not gs.pending_events.is_empty():
		gs.resolve_event(0)
	if gs.can_depart():
		gs.depart()


func test_greedy_player_reaches_third_planet() -> void:
	var step := 30.0
	var game_seconds := 0.0
	var limit := 4.0 * 3600.0  # 4 小时游戏时间（×50 加速下不到 5 分钟真实时间）
	var reached := {1: -1.0, 2: -1.0}
	while game_seconds < limit and gs.planet_index < 2:
		gs.tick(step, true)
		game_seconds += step
		_greedy_step()
		for idx in reached.keys():
			if gs.planet_index >= idx and reached[idx] < 0.0:
				reached[idx] = game_seconds
	assert_eq(gs.planet_index, 2, "应在 %s 内抵达第三个星球，实际耗时 %s" % [
		NumberFormat.format_duration(limit), NumberFormat.format_duration(game_seconds)])
	assert_true(reached[1] > 0.0 and reached[1] < 3600.0, "第二个星球应在 1 小时游戏时间内抵达（实际 %s）" % NumberFormat.format_duration(reached[1]))
	var speed := float(GameData.config["debug"]["speed_multiplier"])
	gut.p("抵达雅利洛-Ⅵ：%s；抵达罗浮：%s；加速 ×%d 下约 %s 真实时间" % [
		NumberFormat.format_duration(reached[1]), NumberFormat.format_duration(reached[2]),
		int(speed), NumberFormat.format_duration(reached[2] / speed)])
	# 一路上应触发了在线事件与抵达事件
	assert_true(gs.triggered_events.size() >= 3)
	assert_true(gs.triggered_events.has("jarilo_snow"))
	assert_true(gs.triggered_events.has("luofu_market"))
	# 终点所有角色都可招募
	gs.resources["jade"] = 1e9
	_greedy_step()
	assert_eq(gs.characters.size(), 4)
	assert_eq(gs.dispatch_slot_count(), 2)
