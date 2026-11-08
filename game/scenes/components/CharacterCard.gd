extends PanelContainer
## 角色卡片：头像色块、名字、被动说明、招募 / 升级按钮、状态。

var char_id: String = ""
var _def: Dictionary = {}

var _level_label: Label
var _passive_label: Label
var _status_label: Label
var _action_button: Button


func setup(def: Dictionary) -> void:
	_def = def
	char_id = def["id"]
	theme_type_variation = &"Card"
	size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var root := UIKit.hbox(24)
	add_child(root)

	var avatar := UIKit.swatch(UIKit.color_from_hex(def.get("color", "#888")), 120)
	root.add_child(avatar)

	var info := UIKit.vbox(6)
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.add_child(info)
	var name_row := UIKit.hbox(16)
	name_row.add_child(UIKit.label(def.get("name", char_id), 44))
	_level_label = UIKit.label("", UIKit.FONT_SMALL, UIKit.COLOR_GOLD)
	name_row.add_child(_level_label)
	info.add_child(name_row)
	info.add_child(UIKit.wrapped_label(def.get("title", ""), UIKit.FONT_TINY, UIKit.COLOR_MUTED))
	_passive_label = UIKit.wrapped_label("", UIKit.FONT_SMALL, UIKit.COLOR_GOOD)
	info.add_child(_passive_label)
	_status_label = UIKit.wrapped_label("", UIKit.FONT_SMALL, UIKit.COLOR_MUTED)
	info.add_child(_status_label)

	_action_button = UIKit.button("招募", &"", 300)
	_action_button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_action_button.pressed.connect(_on_action)
	root.add_child(_action_button)
	refresh()


func _passive_text(level: int) -> String:
	var passive: Dictionary = _def.get("passive", {})
	var value := Economy.passive_value(_def, maxi(level, 1))
	var desc: String = passive.get("desc", "")
	if passive.get("type", "") == "offline_cap_seconds":
		return "%s +%s" % [desc, NumberFormat.format_duration(value)]
	return "%s %s" % [desc, NumberFormat.format_percent(value)]


func refresh() -> void:
	var recruited: bool = GameState.is_recruited(char_id)
	var unlocked: bool = Economy.is_character_unlocked(GameState, char_id)
	var level: int = GameState.character_level(char_id)
	if recruited:
		_level_label.text = "Lv.%d" % level
		_passive_label.text = "被动：" + _passive_text(level)
		if GameState.is_character_dispatched(char_id):
			_status_label.text = "派遣中"
			_status_label.add_theme_color_override("font_color", UIKit.COLOR_GOLD)
		else:
			_status_label.text = "空闲"
			_status_label.add_theme_color_override("font_color", UIKit.COLOR_MUTED)
		if level >= Economy.character_max_level():
			_action_button.text = "已满级"
			_action_button.disabled = true
		else:
			_action_button.text = "升级\n%s 素材" % NumberFormat.format(Economy.character_upgrade_cost(level))
			_action_button.disabled = not GameState.can_upgrade_character(char_id)
	else:
		_level_label.text = ""
		_passive_label.text = "被动：" + _passive_text(1)
		if unlocked:
			_status_label.text = "未招募"
			_status_label.add_theme_color_override("font_color", UIKit.COLOR_MUTED)
			_action_button.text = "招募\n%s 星琼" % NumberFormat.format(Economy.recruit_cost(char_id))
			_action_button.disabled = not GameState.can_recruit(char_id)
		else:
			var idx := GameData.unlock_planet_index("characters", char_id)
			_status_label.text = "抵达 %s 后可招募" % GameData.get_planet_at(idx).get("name", "未知星球")
			_status_label.add_theme_color_override("font_color", UIKit.COLOR_BAD)
			_action_button.text = "未解锁"
			_action_button.disabled = true


func refresh_buttons() -> void:
	if GameState.is_recruited(char_id):
		if GameState.character_level(char_id) < Economy.character_max_level():
			_action_button.disabled = not GameState.can_upgrade_character(char_id)
	elif Economy.is_character_unlocked(GameState, char_id):
		_action_button.disabled = not GameState.can_recruit(char_id)


func _on_action() -> void:
	if GameState.is_recruited(char_id):
		GameState.upgrade_character(char_id)
	else:
		GameState.recruit(char_id)
	refresh()
