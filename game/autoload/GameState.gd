extends Node
## 全局状态与存档。
## 负责：资源累积、车厢/角色/派遣/航行状态、文本事件队列、离线结算、
## user://save.json 的读写与版本迁移、自动保存。

signal resources_changed
signal state_changed
signal event_triggered(event: Dictionary)
signal event_resolved(event: Dictionary, option_index: int)
signal travel_started(target_index: int)
signal travel_finished(planet_index: int)
signal dispatch_changed
signal offline_settled(report: Dictionary)
signal saved
signal debug_speed_changed(enabled: bool)

const SAVE_VERSION := 1
const DEFAULT_SAVE_PATH := "user://save.json"

## 存档路径，测试时可以改成 user://test_save.json。
var save_path: String = DEFAULT_SAVE_PATH
## 为 false 时 _ready 不自动读档/结算离线（单元测试用）。
var auto_boot: bool = true

# --- 运行时状态 --------------------------------------------------------------
var resources: Dictionary = {"jade": 0.0, "fuel": 0.0, "material": 0.0}
var car_levels: Dictionary = {}            # car_id -> int
var characters: Dictionary = {}            # char_id -> level(int)，存在即已招募
var dispatches: Array = []                 # 每个槽位一个 Dictionary；{} 表示空闲
var planet_index: int = 0
var travel: Dictionary = {"active": false, "elapsed": 0.0, "target": 0}
var triggered_events: Array = []           # 已触发过的事件 id（历史）
var pending_events: Array = []             # 等待玩家处理的事件 id 队列
var online_seconds: float = 0.0            # 距离上次在线事件的在线秒数
var settings: Dictionary = {"sound": true, "debug_speed": false}
var stats: Dictionary = {"total_online_seconds": 0.0, "total_offline_seconds": 0.0, "departures": 0}
var last_save_ts: int = 0

## 启动时的离线结算报告（UI 在 _ready 后读取并弹窗），没有则为空。
var pending_offline_report: Dictionary = {}

var _autosave_accum: float = 0.0
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	_rng.randomize()
	if _is_test_run():
		# GUT 命令行跑测试时不读写真实存档，由测试自行构造状态。
		auto_boot = false
		set_process(false)
	if auto_boot:
		boot()


func _exit_tree() -> void:
	if auto_boot:
		save()


static func _is_test_run() -> bool:
	for arg in OS.get_cmdline_args():
		if arg.begins_with("-g") or arg.contains("addons/gut/"):
			return true
	return false


func _notification(what: int) -> void:
	match what:
		NOTIFICATION_APPLICATION_PAUSED, \
		NOTIFICATION_APPLICATION_FOCUS_OUT, \
		NOTIFICATION_WM_GO_BACK_REQUEST, \
		NOTIFICATION_WM_CLOSE_REQUEST:
			if auto_boot:
				save()


func _process(delta: float) -> void:
	var dt := delta * time_scale()
	tick(dt, true)
	_autosave_accum += delta
	var interval := float(GameData.config.get("autosave_interval_seconds", 30))
	if _autosave_accum >= interval:
		_autosave_accum = 0.0
		save()


# ---------------------------------------------------------------------------
# 启动 / 重置
# ---------------------------------------------------------------------------

## 读取存档并结算离线收益；没有存档则开新档。
func boot() -> void:
	reset_state()
	if load_save():
		var elapsed := float(now_ts() - last_save_ts)
		var min_elapsed := float(GameData.config.get("offline", {}).get("min_elapsed_seconds", 10))
		if elapsed >= min_elapsed:
			pending_offline_report = settle_offline(elapsed)
			offline_settled.emit(pending_offline_report)
	else:
		_ensure_dispatch_slots()
	save()


## 回到全新开局（不写盘）。
func reset_state() -> void:
	resources = {"jade": 0.0, "fuel": 0.0, "material": 0.0}
	for res in GameData.get_resources():
		resources[res["id"]] = 0.0
	car_levels = {}
	for car in GameData.cars:
		car_levels[car["id"]] = 0
	characters = {}
	dispatches = []
	planet_index = 0
	travel = {"active": false, "elapsed": 0.0, "target": 0}
	triggered_events = []
	pending_events = []
	online_seconds = 0.0
	settings = {"sound": true, "debug_speed": false}
	stats = {"total_online_seconds": 0.0, "total_offline_seconds": 0.0, "departures": 0}
	last_save_ts = 0
	pending_offline_report = {}
	_ensure_dispatch_slots()
	_apply_sound_setting()
	state_changed.emit()
	resources_changed.emit()


## 删除存档并重新开始。
func reset_save() -> void:
	var abs_path := ProjectSettings.globalize_path(save_path)
	if FileAccess.file_exists(save_path):
		DirAccess.remove_absolute(abs_path)
	reset_state()
	save()


# ---------------------------------------------------------------------------
# 时间
# ---------------------------------------------------------------------------

func now_ts() -> int:
	return int(Time.get_unix_time_from_system())


## 调试加速倍率；关闭时为 1。
func time_scale() -> float:
	if settings.get("debug_speed", false):
		return float(GameData.config.get("debug", {}).get("speed_multiplier", 1.0))
	return 1.0


func set_debug_speed(enabled: bool) -> void:
	settings["debug_speed"] = enabled
	debug_speed_changed.emit(enabled)
	state_changed.emit()


func set_sound(enabled: bool) -> void:
	settings["sound"] = enabled
	_apply_sound_setting()
	state_changed.emit()
	save()


func _apply_sound_setting() -> void:
	# 原型没有音频资源，只预留开关：静音主总线。
	if AudioServer.bus_count > 0:
		AudioServer.set_bus_mute(0, not settings.get("sound", true))


# ---------------------------------------------------------------------------
# 核心推进：产出、派遣、航行、在线事件
# ---------------------------------------------------------------------------

## 推进 dt 秒的游戏时间。online=false 表示离线结算（不累计在线事件计时）。
func tick(dt: float, online: bool = true) -> void:
	if dt <= 0.0:
		return
	var rates := Economy.production_rates(self)
	for id in rates.keys():
		resources[id] = float(resources.get(id, 0.0)) + float(rates[id]) * dt

	var dispatch_dirty := false
	for d in dispatches:
		if d.is_empty():
			continue
		if float(d.get("remaining", 0.0)) > 0.0:
			d["remaining"] = maxf(float(d["remaining"]) - dt, 0.0)
			dispatch_dirty = true

	if travel.get("active", false):
		travel["elapsed"] = float(travel.get("elapsed", 0.0)) + dt
		if travel["elapsed"] >= Economy.travel_seconds(self):
			_arrive()

	if online:
		online_seconds += dt
		stats["total_online_seconds"] = float(stats.get("total_online_seconds", 0.0)) + dt
		var interval := float(GameData.config.get("events", {}).get("online_interval_seconds", 600))
		if interval > 0.0 and online_seconds >= interval:
			online_seconds = fmod(online_seconds, interval)
			trigger_event("online")

	resources_changed.emit()
	if dispatch_dirty:
		dispatch_changed.emit()


# ---------------------------------------------------------------------------
# 离线结算
# ---------------------------------------------------------------------------

## 按 min(elapsed, 上限) 结算自动产出、派遣与航行进度，返回结算报告。
func settle_offline(elapsed_seconds: float) -> Dictionary:
	var cap := Economy.offline_cap_seconds(self)
	var effective := clampf(elapsed_seconds, 0.0, cap)
	var before := resources.duplicate()
	var active_before := _count_running_dispatches()
	var planet_before := planet_index

	tick(effective, false)

	var gains := {}
	for id in resources.keys():
		gains[id] = float(resources[id]) - float(before.get(id, 0.0))
	var completed := active_before - _count_running_dispatches()
	stats["total_offline_seconds"] = float(stats.get("total_offline_seconds", 0.0)) + effective

	return {
		"elapsed": elapsed_seconds,
		"effective": effective,
		"cap": cap,
		"capped": elapsed_seconds > cap,
		"gains": gains,
		"dispatches_completed": completed,
		"arrived": planet_index > planet_before,
	}


func _count_running_dispatches() -> int:
	var n := 0
	for d in dispatches:
		if not d.is_empty() and float(d.get("remaining", 0.0)) > 0.0:
			n += 1
	return n


# ---------------------------------------------------------------------------
# 车厢
# ---------------------------------------------------------------------------

func car_level(car_id: String) -> int:
	return int(car_levels.get(car_id, 0))


func can_upgrade_car(car_id: String) -> bool:
	if not Economy.is_car_unlocked(self, car_id):
		return false
	return float(resources.get("jade", 0.0)) >= Economy.upgrade_cost(car_id, car_level(car_id))


func upgrade_car(car_id: String) -> bool:
	if not can_upgrade_car(car_id):
		return false
	var cost := Economy.upgrade_cost(car_id, car_level(car_id))
	resources["jade"] = float(resources["jade"]) - cost
	car_levels[car_id] = car_level(car_id) + 1
	state_changed.emit()
	resources_changed.emit()
	save()
	return true


# ---------------------------------------------------------------------------
# 角色
# ---------------------------------------------------------------------------

func is_recruited(char_id: String) -> bool:
	return characters.has(char_id)


func character_level(char_id: String) -> int:
	return int(characters.get(char_id, 0))


func can_recruit(char_id: String) -> bool:
	if is_recruited(char_id) or not Economy.is_character_unlocked(self, char_id):
		return false
	return float(resources.get("jade", 0.0)) >= Economy.recruit_cost(char_id)


func recruit(char_id: String) -> bool:
	if not can_recruit(char_id):
		return false
	resources["jade"] = float(resources["jade"]) - Economy.recruit_cost(char_id)
	characters[char_id] = 1
	state_changed.emit()
	resources_changed.emit()
	save()
	return true


func can_upgrade_character(char_id: String) -> bool:
	if not is_recruited(char_id):
		return false
	var level := character_level(char_id)
	if level >= Economy.character_max_level():
		return false
	return float(resources.get("material", 0.0)) >= Economy.character_upgrade_cost(level)


func upgrade_character(char_id: String) -> bool:
	if not can_upgrade_character(char_id):
		return false
	var level := character_level(char_id)
	resources["material"] = float(resources["material"]) - Economy.character_upgrade_cost(level)
	characters[char_id] = level + 1
	state_changed.emit()
	resources_changed.emit()
	save()
	return true


# ---------------------------------------------------------------------------
# 派遣
# ---------------------------------------------------------------------------

func _ensure_dispatch_slots() -> void:
	var slots := Economy.dispatch_slots(self)
	while dispatches.size() < slots:
		dispatches.append({})


func dispatch_slot_count() -> int:
	return Economy.dispatch_slots(self)


func is_character_dispatched(char_id: String) -> bool:
	for d in dispatches:
		if not d.is_empty() and d.get("char_id", "") == char_id:
			return true
	return false


## 可以派遣的角色：已招募且不在任务中。
func idle_characters() -> Array:
	var out: Array = []
	for id in characters.keys():
		if not is_character_dispatched(id):
			out.append(id)
	return out


func get_dispatch(slot: int) -> Dictionary:
	if slot < 0 or slot >= dispatches.size():
		return {}
	return dispatches[slot]


func start_dispatch(slot: int, char_id: String, duration_id: String) -> bool:
	_ensure_dispatch_slots()
	if slot < 0 or slot >= dispatches.size():
		return false
	if not dispatches[slot].is_empty():
		return false
	if not is_recruited(char_id) or is_character_dispatched(char_id):
		return false
	var duration := GameData.get_duration(duration_id)
	if duration.is_empty():
		return false
	var seconds := float(duration.get("seconds", 0.0))
	dispatches[slot] = {
		"char_id": char_id,
		"duration_id": duration_id,
		"total": seconds,
		"remaining": seconds,
		"reward": Economy.dispatch_reward(self, duration_id),
	}
	dispatch_changed.emit()
	state_changed.emit()
	save()
	return true


func is_dispatch_complete(slot: int) -> bool:
	var d := get_dispatch(slot)
	return not d.is_empty() and float(d.get("remaining", 0.0)) <= 0.0


## 收取已完成的派遣，返回获得的素材数量（失败返回 0）。
func collect_dispatch(slot: int) -> float:
	if not is_dispatch_complete(slot):
		return 0.0
	var d: Dictionary = dispatches[slot]
	var reward := float(d.get("reward", 0.0))
	resources["material"] = float(resources.get("material", 0.0)) + reward
	dispatches[slot] = {}
	dispatch_changed.emit()
	state_changed.emit()
	resources_changed.emit()
	save()
	return reward


# ---------------------------------------------------------------------------
# 星球与航行
# ---------------------------------------------------------------------------

func current_planet() -> Dictionary:
	return GameData.get_planet_at(planet_index)


func next_planet() -> Dictionary:
	return GameData.get_planet_at(planet_index + 1)


func has_next_planet() -> bool:
	return not next_planet().is_empty()


func is_traveling() -> bool:
	return bool(travel.get("active", false))


## 航行进度 0..1
func travel_progress() -> float:
	if not is_traveling():
		return 0.0
	return clampf(float(travel.get("elapsed", 0.0)) / Economy.travel_seconds(self), 0.0, 1.0)


func travel_remaining_seconds() -> float:
	if not is_traveling():
		return 0.0
	return maxf(Economy.travel_seconds(self) - float(travel.get("elapsed", 0.0)), 0.0)


func can_depart() -> bool:
	if is_traveling() or not has_next_planet():
		return false
	return float(resources.get("fuel", 0.0)) >= Economy.next_planet_fuel_cost(self)


func depart() -> bool:
	if not can_depart():
		return false
	resources["fuel"] = float(resources["fuel"]) - Economy.next_planet_fuel_cost(self)
	travel = {"active": true, "elapsed": 0.0, "target": planet_index + 1}
	stats["departures"] = int(stats.get("departures", 0)) + 1
	travel_started.emit(planet_index + 1)
	state_changed.emit()
	resources_changed.emit()
	save()
	return true


func _arrive() -> void:
	var target := mini(int(travel.get("target", planet_index + 1)), GameData.planets.size() - 1)
	planet_index = target
	travel = {"active": false, "elapsed": 0.0, "target": target}
	_ensure_dispatch_slots()
	travel_finished.emit(planet_index)
	trigger_event("arrival")
	state_changed.emit()
	dispatch_changed.emit()


# ---------------------------------------------------------------------------
# 文本事件
# ---------------------------------------------------------------------------

## 触发一条事件（kind: "arrival" | "online"），加入待处理队列。
func trigger_event(kind: String) -> Dictionary:
	var ev := pick_event(kind)
	if ev.is_empty():
		return {}
	var id: String = ev["id"]
	if not triggered_events.has(id):
		triggered_events.append(id)
	pending_events.append(id)
	event_triggered.emit(ev)
	return ev


## 选事件：抵达时优先当前星球的专属事件，其次是通用事件；优先没见过的。
func pick_event(kind: String) -> Dictionary:
	var planet_id: String = current_planet().get("id", "")
	var pools: Array = []
	if kind == "arrival":
		pools.append(GameData.events.filter(
			func(e): return e.get("trigger", "any") == "arrival" and e.get("planet", "") == planet_id))
	pools.append(GameData.events.filter(
		func(e): return e.get("trigger", "any") in ["any", kind]))

	for pool in pools:
		var unseen: Array = pool.filter(func(e): return not triggered_events.has(e["id"]))
		if not unseen.is_empty():
			return unseen[_rng.randi_range(0, unseen.size() - 1)]
	var generic: Array = pools.back()
	if generic.is_empty():
		return {}
	return generic[_rng.randi_range(0, generic.size() - 1)]


func current_pending_event() -> Dictionary:
	if pending_events.is_empty():
		return {}
	return GameData.get_event(pending_events[0])


## 玩家对队首事件做出选择，应用效果并移出队列。返回实际的资源变化。
func resolve_event(option_index: int) -> Dictionary:
	var ev := current_pending_event()
	if ev.is_empty():
		return {}
	pending_events.pop_front()
	var options: Array = ev.get("options", [])
	var changes := {}
	if option_index >= 0 and option_index < options.size():
		changes = apply_effects(options[option_index].get("effects", []))
	event_resolved.emit(ev, option_index)
	state_changed.emit()
	resources_changed.emit()
	save()
	return changes


## 应用一组效果，返回 {资源: 变化量}。
func apply_effects(effects: Array) -> Dictionary:
	var changes := {}
	for eff in effects:
		var type: String = eff.get("type", "")
		var value := float(eff.get("value", 0.0))
		var res_id := ""
		var delta := 0.0
		match type:
			"jade_percent":
				res_id = "jade"
				delta = floorf(float(resources.get("jade", 0.0)) * value)
			"jade", "fuel", "material":
				res_id = type
				delta = value
			_:
				push_warning("未知事件效果类型：%s" % type)
				continue
		var new_value := maxf(float(resources.get(res_id, 0.0)) + delta, 0.0)
		delta = new_value - float(resources.get(res_id, 0.0))
		resources[res_id] = new_value
		changes[res_id] = float(changes.get(res_id, 0.0)) + delta
	return changes


## 事件选项效果的文字描述，例如 "星琼 +5%、素材 +20"。
func describe_effects(effects: Array) -> String:
	var parts: Array[String] = []
	for eff in effects:
		var type: String = eff.get("type", "")
		var value := float(eff.get("value", 0.0))
		match type:
			"jade_percent":
				parts.append("星琼 %s" % NumberFormat.format_percent(value))
			"jade", "fuel", "material":
				parts.append("%s %s%s" % [GameData.resource_name(type), "+" if value >= 0 else "", NumberFormat.format(value)])
	return "、".join(parts)


# ---------------------------------------------------------------------------
# 存档
# ---------------------------------------------------------------------------

func to_dict() -> Dictionary:
	return {
		"version": SAVE_VERSION,
		"saved_at": last_save_ts,
		"resources": resources.duplicate(),
		"car_levels": car_levels.duplicate(),
		"characters": characters.duplicate(),
		"dispatches": dispatches.duplicate(true),
		"planet_index": planet_index,
		"travel": travel.duplicate(),
		"triggered_events": triggered_events.duplicate(),
		"pending_events": pending_events.duplicate(),
		"online_seconds": online_seconds,
		"settings": settings.duplicate(),
		"stats": stats.duplicate(),
	}


func from_dict(data: Dictionary) -> void:
	data = migrate(data)
	reset_state()
	last_save_ts = int(data.get("saved_at", 0))
	var res: Dictionary = data.get("resources", {})
	for id in resources.keys():
		resources[id] = float(res.get(id, 0.0))
	var levels: Dictionary = data.get("car_levels", {})
	for id in car_levels.keys():
		car_levels[id] = int(levels.get(id, 0))
	characters = {}
	var chars: Dictionary = data.get("characters", {})
	for id in chars.keys():
		if not GameData.get_character(id).is_empty():
			characters[id] = maxi(int(chars[id]), 1)
	planet_index = clampi(int(data.get("planet_index", 0)), 0, maxi(GameData.planets.size() - 1, 0))
	var t: Dictionary = data.get("travel", {})
	travel = {
		"active": bool(t.get("active", false)),
		"elapsed": float(t.get("elapsed", 0.0)),
		"target": int(t.get("target", planet_index)),
	}
	dispatches = []
	for d in data.get("dispatches", []):
		if d is Dictionary and not d.is_empty() and GameData.get_character(d.get("char_id", "")).is_empty() == false:
			dispatches.append({
				"char_id": String(d.get("char_id", "")),
				"duration_id": String(d.get("duration_id", "")),
				"total": float(d.get("total", 0.0)),
				"remaining": float(d.get("remaining", 0.0)),
				"reward": float(d.get("reward", 0.0)),
			})
		else:
			dispatches.append({})
	_ensure_dispatch_slots()
	triggered_events = []
	for id in data.get("triggered_events", []):
		triggered_events.append(String(id))
	pending_events = []
	for id in data.get("pending_events", []):
		if not GameData.get_event(String(id)).is_empty():
			pending_events.append(String(id))
	online_seconds = float(data.get("online_seconds", 0.0))
	var s: Dictionary = data.get("settings", {})
	settings = {
		"sound": bool(s.get("sound", true)),
		"debug_speed": bool(s.get("debug_speed", false)),
	}
	var st: Dictionary = data.get("stats", {})
	stats = {
		"total_online_seconds": float(st.get("total_online_seconds", 0.0)),
		"total_offline_seconds": float(st.get("total_offline_seconds", 0.0)),
		"departures": int(st.get("departures", 0)),
	}
	_apply_sound_setting()
	state_changed.emit()
	resources_changed.emit()
	dispatch_changed.emit()


## 旧版本存档迁移：逐版本升级直到 SAVE_VERSION。
static func migrate(data: Dictionary) -> Dictionary:
	var out := data.duplicate(true)
	var version := int(out.get("version", 0))
	while version < SAVE_VERSION:
		match version:
			0:
				# v0：无版本号的早期存档，字段与 v1 兼容，只补版本号。
				pass
		version += 1
		out["version"] = version
	return out


func save() -> bool:
	last_save_ts = now_ts()
	var file := FileAccess.open(save_path, FileAccess.WRITE)
	if file == null:
		push_error("GameState: 无法写入存档 %s (%s)" % [save_path, FileAccess.get_open_error()])
		return false
	file.store_string(JSON.stringify(to_dict(), "\t"))
	file.close()
	saved.emit()
	return true


## 读档成功返回 true；文件不存在或损坏返回 false（状态保持为新档）。
func load_save() -> bool:
	if not FileAccess.file_exists(save_path):
		return false
	var text := FileAccess.get_file_as_string(save_path)
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null or not (parsed is Dictionary):
		push_warning("GameState: 存档损坏，已忽略：%s" % save_path)
		return false
	from_dict(parsed)
	return true
