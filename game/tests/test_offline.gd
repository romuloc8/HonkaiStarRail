extends GutTest
## 离线结算：按 min(离线秒数, 上限) 结算产出、派遣与航行。

var gs: Node


func before_each() -> void:
	gs = StateFactory.make_state(self)


func after_each() -> void:
	gs.free()


func test_offline_gain_equals_rate_times_time() -> void:
	gs.car_levels["passenger"] = 2
	var rate_jade := Economy.production_rate(gs, "jade")
	var rate_fuel := Economy.production_rate(gs, "fuel")
	var report: Dictionary = gs.settle_offline(600.0)
	assert_almost_eq(report["effective"], 600.0, 0.001)
	assert_false(report["capped"])
	assert_almost_eq(report["gains"]["jade"], rate_jade * 600.0, 0.01)
	assert_almost_eq(report["gains"]["fuel"], rate_fuel * 600.0, 0.01)
	assert_almost_eq(gs.resources["jade"], rate_jade * 600.0, 0.01)


func test_offline_is_capped() -> void:
	var cap := Economy.offline_cap_seconds(gs)
	var rate_jade := Economy.production_rate(gs, "jade")
	var report: Dictionary = gs.settle_offline(cap * 3.0)
	assert_true(report["capped"])
	assert_almost_eq(report["effective"], cap, 0.001)
	assert_almost_eq(report["gains"]["jade"], rate_jade * cap, 0.5)


func test_offline_cap_grows_with_cargo_and_welt() -> void:
	gs.car_levels["cargo"] = 1
	gs.characters["welt"] = 1
	var expected_cap := float(GameData.config["offline"]["base_cap_seconds"]) + 1800.0 + 7200.0
	var report: Dictionary = gs.settle_offline(999999.0)
	assert_almost_eq(report["cap"], expected_cap, 0.001)
	assert_almost_eq(report["effective"], expected_cap, 0.001)


func test_offline_advances_dispatch() -> void:
	gs.characters["march7"] = 1
	assert_true(gs.start_dispatch(0, "march7", "short"))
	assert_false(gs.is_dispatch_complete(0))
	var report: Dictionary = gs.settle_offline(300.0)
	assert_eq(report["dispatches_completed"], 0)
	assert_almost_eq(gs.get_dispatch(0)["remaining"], 300.0, 0.001)
	report = gs.settle_offline(400.0)
	assert_eq(report["dispatches_completed"], 1)
	assert_true(gs.is_dispatch_complete(0))
	assert_eq(gs.get_dispatch(0)["remaining"], 0.0)


func test_offline_does_not_trigger_online_events() -> void:
	gs.settle_offline(3600.0)
	assert_eq(gs.pending_events.size(), 0)
	assert_almost_eq(gs.online_seconds, 0.0, 0.001)


func test_offline_completes_travel_and_queues_arrival_event() -> void:
	gs.resources["fuel"] = 500.0
	assert_true(gs.depart())
	assert_true(gs.is_traveling())
	var report: Dictionary = gs.settle_offline(120.0)
	assert_true(report["arrived"])
	assert_false(gs.is_traveling())
	assert_eq(gs.planet_index, 1)
	assert_eq(gs.pending_events.size(), 1)
	assert_eq(gs.pending_events[0], "jarilo_snow", "抵达雅利洛-Ⅵ优先触发专属事件")


func test_negative_or_zero_elapsed_is_noop() -> void:
	var report: Dictionary = gs.settle_offline(0.0)
	assert_eq(report["gains"]["jade"], 0.0)
	report = gs.settle_offline(-50.0)
	assert_eq(report["effective"], 0.0)
	assert_eq(gs.resources["jade"], 0.0)


func test_online_tick_triggers_event_every_interval() -> void:
	var interval := float(GameData.config["events"]["online_interval_seconds"])
	gs.tick(interval - 1.0, true)
	assert_eq(gs.pending_events.size(), 0)
	gs.tick(2.0, true)
	assert_eq(gs.pending_events.size(), 1)
	assert_almost_eq(gs.online_seconds, 1.0, 0.001)


func test_debug_speed_scales_time() -> void:
	assert_eq(gs.time_scale(), 1.0)
	gs.set_debug_speed(true)
	assert_eq(gs.time_scale(), float(GameData.config["debug"]["speed_multiplier"]))
	gs.set_debug_speed(false)
	assert_eq(gs.time_scale(), 1.0)
