extends PanelContainer
## 车厢卡片：名称、等级、效果说明、升级按钮；未解锁时显示解锁条件。

var car_id: String = ""
var _def: Dictionary = {}

var _level_label: Label
var _effect_label: Label
var _upgrade_button: Button
var _lock_label: Label


func setup(def: Dictionary) -> void:
	_def = def
	car_id = def["id"]
	theme_type_variation = &"Card"
	size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var root := UIKit.hbox(24)
	add_child(root)

	root.add_child(UIKit.swatch(UIKit.color_from_hex(def.get("color", "#888")), 110, 24))

	var info := UIKit.vbox(6)
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.add_child(info)
	var name_row := UIKit.hbox(16)
	name_row.add_child(UIKit.label(def.get("name", car_id), 44))
	_level_label = UIKit.label("Lv.0", UIKit.FONT_SMALL, UIKit.COLOR_GOLD)
	name_row.add_child(_level_label)
	info.add_child(name_row)
	info.add_child(UIKit.wrapped_label(def.get("desc", ""), UIKit.FONT_SMALL, UIKit.COLOR_MUTED))
	_effect_label = UIKit.wrapped_label("", UIKit.FONT_SMALL, UIKit.COLOR_GOOD)
	info.add_child(_effect_label)
	_lock_label = UIKit.wrapped_label("", UIKit.FONT_SMALL, UIKit.COLOR_BAD)
	info.add_child(_lock_label)

	_upgrade_button = UIKit.button("升级", &"", 300)
	_upgrade_button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_upgrade_button.pressed.connect(_on_upgrade)
	root.add_child(_upgrade_button)

	refresh()


func refresh() -> void:
	var level: int = GameState.car_level(car_id)
	var unlocked: bool = Economy.is_car_unlocked(GameState, car_id)
	_level_label.text = "Lv.%d" % level
	_lock_label.visible = not unlocked
	_effect_label.visible = unlocked
	if unlocked:
		var parts: Array[String] = []
		for eff in _def.get("effects", []):
			var total := float(eff.get("per_level", 0.0)) * level
			match eff.get("type", ""):
				"offline_cap_seconds":
					parts.append("离线上限 +%s" % NumberFormat.format_duration(total))
				_:
					parts.append("当前 %s" % NumberFormat.format_percent(total))
		_effect_label.text = "　".join(parts)
		var cost := Economy.upgrade_cost(car_id, level)
		_upgrade_button.text = "升级\n%s 星琼" % NumberFormat.format(cost)
		_upgrade_button.disabled = not GameState.can_upgrade_car(car_id)
	else:
		var idx := GameData.unlock_planet_index("cars", car_id)
		var planet := GameData.get_planet_at(idx)
		_lock_label.text = "抵达 %s 后解锁" % planet.get("name", "未知星球")
		_upgrade_button.text = "未解锁"
		_upgrade_button.disabled = true


## 只刷新按钮可用状态（随资源每帧变化）。
func refresh_buttons() -> void:
	if Economy.is_car_unlocked(GameState, car_id):
		_upgrade_button.disabled = not GameState.can_upgrade_car(car_id)


func _on_upgrade() -> void:
	GameState.upgrade_car(car_id)
	refresh()
