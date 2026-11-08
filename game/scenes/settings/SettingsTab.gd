extends Control
## 设置页：音量开关、调试加速、手动保存、重置存档、版本信息。

@onready var _list: VBoxContainer = $Scroll/Margin/List

var _sound_toggle: Button
var _debug_toggle: Button
var _stats_label: Label
var _save_label: Label


func _ready() -> void:
	_build()
	GameState.state_changed.connect(refresh)
	GameState.saved.connect(_on_saved)
	refresh()


func _build() -> void:
	_list.add_child(UIKit.label("设置", 48, UIKit.COLOR_GOLD))

	var panel := PanelContainer.new()
	var box := UIKit.vbox(12)
	panel.add_child(box)

	var sound := UIKit.toggle_row("音效\n（原型暂无音频，仅预留开关）", func(on): GameState.set_sound(on))
	_sound_toggle = sound["button"]
	box.add_child(sound["row"])
	box.add_child(UIKit.separator())

	var multiplier := NumberFormat.format(float(GameData.config.get("debug", {}).get("speed_multiplier", 1.0)))
	var debug := UIKit.toggle_row("调试加速 ×%s" % multiplier, func(on): GameState.set_debug_speed(on))
	_debug_toggle = debug["button"]
	box.add_child(debug["row"])
	box.add_child(UIKit.wrapped_label("开启后产出、航行、派遣与在线事件计时全部加速，用于快速验证整条流程；离线收益仍按真实时间计算。", UIKit.FONT_TINY, UIKit.COLOR_MUTED))
	_list.add_child(panel)

	# 存档
	var save_panel := PanelContainer.new()
	var save_box := UIKit.vbox(16)
	save_panel.add_child(save_box)
	save_box.add_child(UIKit.label("存档", 40, UIKit.COLOR_GOLD))
	_save_label = UIKit.wrapped_label("", UIKit.FONT_TINY, UIKit.COLOR_MUTED)
	save_box.add_child(_save_label)
	var save_button := UIKit.button("立即保存", &"SecondaryButton")
	save_button.pressed.connect(func(): GameState.save())
	save_box.add_child(save_button)
	var reset_button := UIKit.button("重置存档", &"DangerButton")
	reset_button.pressed.connect(_on_reset_pressed)
	save_box.add_child(reset_button)
	_list.add_child(save_panel)

	# 统计与版本
	var about := PanelContainer.new()
	var about_box := UIKit.vbox(10)
	about.add_child(about_box)
	about_box.add_child(UIKit.label("关于", 40, UIKit.COLOR_GOLD))
	_stats_label = UIKit.wrapped_label("", UIKit.FONT_TINY, UIKit.COLOR_MUTED)
	about_box.add_child(_stats_label)
	var version: String = str(ProjectSettings.get_setting("application/config/version", "0.0.0"))
	about_box.add_child(UIKit.label("版本 %s · Godot %s" % [version, Engine.get_version_info().get("string", "")], UIKit.FONT_TINY, UIKit.COLOR_MUTED))
	about_box.add_child(UIKit.wrapped_label("《星穹列车·远航》是基于《崩坏：星穹铁道》世界观的同人练习作品，不含任何官方素材，不作商业用途。", UIKit.FONT_TINY, UIKit.COLOR_MUTED))
	_list.add_child(about)


func refresh() -> void:
	if not is_node_ready():
		return
	UIKit.set_toggle(_sound_toggle, bool(GameState.settings.get("sound", true)))
	UIKit.set_toggle(_debug_toggle, bool(GameState.settings.get("debug_speed", false)))
	var stats: Dictionary = GameState.stats
	_stats_label.text = "累计在线 %s · 累计离线结算 %s · 启航 %d 次 · 已触发事件 %d 条" % [
		NumberFormat.format_duration(float(stats.get("total_online_seconds", 0.0))),
		NumberFormat.format_duration(float(stats.get("total_offline_seconds", 0.0))),
		int(stats.get("departures", 0)),
		GameState.triggered_events.size(),
	]
	_on_saved()


func _on_saved() -> void:
	if _save_label == null:
		return
	var ts: int = GameState.last_save_ts
	var bias_seconds: int = int(Time.get_time_zone_from_system().get("bias", 0)) * 60
	var when := Time.get_datetime_string_from_unix_time(ts + bias_seconds, true) if ts > 0 else "尚未保存"
	_save_label.text = "存档位置：%s\n上次保存：%s（每 30 秒、关键操作后、切到后台时自动保存）" % [GameState.save_path, when]


func _on_reset_pressed() -> void:
	var main := get_tree().get_first_node_in_group("main")
	if main == null or not main.has_method("confirm"):
		GameState.reset_save()
		return
	main.call("confirm", "重置存档", "将删除全部进度（资源、车厢、角色、派遣、星球）并重新开始。此操作无法撤销。", func():
		GameState.reset_save()
		refresh(), "确认重置", true)
