extends PanelContainer
## 派遣槽位：空闲时显示“派遣”按钮；任务中显示角色、倒计时与进度；完成后显示“收取”。

signal dispatch_requested(slot: int)

var slot: int = 0

var _title_label: Label
var _info_label: Label
var _bar: ProgressBar
var _button: Button
var _avatar: Panel
var _avatar_char := ""


func _set_avatar(char_id: String, color: Color) -> void:
	if _avatar_char == char_id:
		return
	_avatar_char = char_id
	_avatar.add_theme_stylebox_override("panel", _make_style(color))


func setup(slot_index: int) -> void:
	slot = slot_index
	theme_type_variation = &"Card"
	size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var root := UIKit.hbox(24)
	add_child(root)
	_avatar = UIKit.swatch(Color(0.2, 0.26, 0.46), 110)
	_avatar_char = ""
	root.add_child(_avatar)

	var info := UIKit.vbox(8)
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.add_child(info)
	_title_label = UIKit.label("派遣槽位 %d" % (slot + 1), 40)
	info.add_child(_title_label)
	_info_label = UIKit.wrapped_label("", UIKit.FONT_SMALL, UIKit.COLOR_MUTED)
	info.add_child(_info_label)
	_bar = UIKit.progress_bar(28)
	info.add_child(_bar)

	_button = UIKit.button("派遣", &"", 300)
	_button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_button.pressed.connect(_on_button)
	root.add_child(_button)
	refresh()


func refresh() -> void:
	var d: Dictionary = GameState.get_dispatch(slot)
	if d.is_empty():
		_set_avatar("", Color(0.2, 0.26, 0.46))
		_title_label.text = "派遣槽位 %d · 空闲" % (slot + 1)
		var idle: Array = GameState.idle_characters()
		_info_label.text = "选择一名空闲角色执行任务，获得素材。" if not idle.is_empty() else "没有空闲角色可派遣。"
		_bar.visible = false
		_button.text = "派遣"
		_button.theme_type_variation = &""
		_button.disabled = idle.is_empty()
		return

	var def: Dictionary = GameData.get_character(d.get("char_id", ""))
	var duration: Dictionary = GameData.get_duration(d.get("duration_id", ""))
	_set_avatar(String(d.get("char_id", "")), UIKit.color_from_hex(def.get("color", "#888")))
	_title_label.text = "%s · %s" % [def.get("name", "?"), duration.get("name", "")]
	_bar.visible = true
	var total := float(d.get("total", 1.0))
	var remaining := float(d.get("remaining", 0.0))
	_bar.value = clampf(1.0 - remaining / maxf(total, 0.001), 0.0, 1.0)
	var reward := NumberFormat.format(float(d.get("reward", 0.0)))
	if remaining <= 0.0:
		_info_label.text = "任务完成！可领取 %s 素材。" % reward
		_button.text = "收取\n+%s 素材" % reward
		_button.theme_type_variation = &""
		_button.disabled = false
	else:
		_info_label.text = "剩余 %s，完成后获得 %s 素材。" % [NumberFormat.format_clock(remaining / GameState.time_scale()), reward]
		_button.text = "进行中"
		_button.theme_type_variation = &"SecondaryButton"
		_button.disabled = true


func _make_style(color: Color) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(55)
	sb.border_color = color.lightened(0.35)
	sb.set_border_width_all(3)
	return sb


func _on_button() -> void:
	if GameState.is_dispatch_complete(slot):
		GameState.collect_dispatch(slot)
		refresh()
	elif GameState.get_dispatch(slot).is_empty():
		dispatch_requested.emit(slot)
