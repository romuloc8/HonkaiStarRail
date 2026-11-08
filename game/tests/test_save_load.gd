extends GutTest
## 存档读写、版本迁移与损坏存档处理。

var gs: Node


func before_each() -> void:
	StateFactory.remove_test_save()
	gs = StateFactory.make_state(self)


func after_each() -> void:
	gs.free()
	StateFactory.remove_test_save()


func _populate(state: Node) -> void:
	state.resources["jade"] = 1234.5
	state.resources["fuel"] = 77.0
	state.resources["material"] = 40.0
	state.car_levels["power"] = 3
	state.car_levels["passenger"] = 5
	state.characters["march7"] = 2
	state.characters["danheng"] = 1
	state.planet_index = 1
	state.travel = {"active": true, "elapsed": 12.5, "target": 2}
	state.triggered_events = ["pom_pom_audit", "jarilo_snow"]
	state.pending_events = ["jarilo_snow"]
	state.online_seconds = 123.0
	state.settings["sound"] = false
	state.settings["debug_speed"] = true
	assert_true(state.start_dispatch(0, "march7", "medium"))


func test_save_creates_file_with_version() -> void:
	assert_true(gs.save())
	assert_true(FileAccess.file_exists(StateFactory.TEST_SAVE_PATH))
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(StateFactory.TEST_SAVE_PATH))
	assert_true(parsed is Dictionary)
	assert_eq(int(parsed["version"]), gs.SAVE_VERSION)
	assert_true(int(parsed["saved_at"]) > 0)


func test_round_trip_preserves_state() -> void:
	_populate(gs)
	assert_true(gs.save())

	var other: Node = StateFactory.make_state(self)
	assert_true(other.load_save())
	assert_almost_eq(other.resources["jade"], 1234.5, 0.0001)
	assert_almost_eq(other.resources["fuel"], 77.0, 0.0001)
	assert_almost_eq(other.resources["material"], 40.0, 0.0001)
	assert_eq(other.car_level("power"), 3)
	assert_eq(other.car_level("passenger"), 5)
	assert_eq(other.car_level("cargo"), 0)
	assert_eq(other.character_level("march7"), 2)
	assert_eq(other.character_level("danheng"), 1)
	assert_false(other.is_recruited("himeko"))
	assert_eq(other.planet_index, 1)
	assert_true(other.is_traveling())
	assert_almost_eq(other.travel["elapsed"], 12.5, 0.0001)
	assert_eq(other.travel["target"], 2)
	assert_eq(other.triggered_events, ["pom_pom_audit", "jarilo_snow"])
	assert_eq(other.pending_events, ["jarilo_snow"])
	assert_almost_eq(other.online_seconds, 123.0, 0.0001)
	assert_false(other.settings["sound"])
	assert_true(other.settings["debug_speed"])
	var d: Dictionary = other.get_dispatch(0)
	assert_eq(d["char_id"], "march7")
	assert_eq(d["duration_id"], "medium")
	assert_almost_eq(d["remaining"], 1800.0, 0.0001)
	assert_eq(other.last_save_ts, gs.last_save_ts)
	other.free()


func test_load_missing_file_returns_false() -> void:
	assert_false(gs.load_save())
	assert_eq(gs.resources["jade"], 0.0)


func test_load_corrupt_file_returns_false() -> void:
	var f := FileAccess.open(StateFactory.TEST_SAVE_PATH, FileAccess.WRITE)
	f.store_string("{ this is not json")
	f.close()
	assert_false(gs.load_save())
	assert_eq(gs.planet_index, 0)


func test_migrate_adds_version() -> void:
	var legacy := {"resources": {"jade": 5.0}}
	var migrated: Dictionary = gs.migrate(legacy)
	assert_eq(int(migrated["version"]), gs.SAVE_VERSION)
	assert_eq(int(legacy.get("version", 0)), 0, "migrate 不应修改原字典")


func test_from_dict_ignores_unknown_ids_and_clamps() -> void:
	gs.from_dict({
		"version": 1,
		"characters": {"march7": 1, "nobody": 3},
		"car_levels": {"power": 2, "ghost_car": 9},
		"planet_index": 99,
		"pending_events": ["not_an_event", "march_photo"],
	})
	assert_true(gs.is_recruited("march7"))
	assert_false(gs.is_recruited("nobody"))
	assert_eq(gs.car_level("power"), 2)
	assert_false(gs.car_levels.has("ghost_car"))
	assert_eq(gs.planet_index, GameData.planets.size() - 1)
	assert_eq(gs.pending_events, ["march_photo"])


func test_boot_settles_offline_from_saved_timestamp() -> void:
	gs.car_levels["passenger"] = 1
	gs.save()
	# 把存档时间改到 1 小时前
	var parsed: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(StateFactory.TEST_SAVE_PATH))
	parsed["saved_at"] = int(parsed["saved_at"]) - 3600
	var f := FileAccess.open(StateFactory.TEST_SAVE_PATH, FileAccess.WRITE)
	f.store_string(JSON.stringify(parsed))
	f.close()

	var other: Node = StateFactory.make_state(self)
	other.boot()
	var report: Dictionary = other.pending_offline_report
	assert_false(report.is_empty(), "应产生离线结算报告")
	assert_between(report["elapsed"], 3600.0, 3700.0)
	var rate := Economy.production_rate(other, "jade")
	assert_almost_eq(report["gains"]["jade"], rate * report["effective"], 0.01)
	assert_eq(other.car_level("passenger"), 1)
	other.free()


func test_boot_without_save_starts_fresh_and_writes_file() -> void:
	gs.boot()
	assert_true(gs.pending_offline_report.is_empty())
	assert_true(FileAccess.file_exists(StateFactory.TEST_SAVE_PATH))
	assert_eq(gs.dispatches.size(), 1)


func test_reset_save_deletes_file_and_state() -> void:
	_populate(gs)
	gs.save()
	gs.reset_save()
	assert_eq(gs.resources["jade"], 0.0)
	assert_eq(gs.planet_index, 0)
	assert_false(gs.is_recruited("march7"))
	assert_true(FileAccess.file_exists(StateFactory.TEST_SAVE_PATH), "重置后会写入一份新档")
