extends Control
## 星图页：三个星球的解锁状态、当前位置与航行进度。

@onready var _list: VBoxContainer = $Scroll/Margin/List

var _cards: Array = []   # 每个元素 {"panel", "status", "bar", "unlock"}


func _ready() -> void:
	_build()
	GameState.state_changed.connect(refresh)
	GameState.travel_started.connect(func(_i): refresh())
	GameState.travel_finished.connect(func(_i): refresh())
	GameState.resources_changed.connect(_refresh_bars)
	refresh()


func _build() -> void:
	_list.add_child(UIKit.label("星图", 48, UIKit.COLOR_GOLD))
	_list.add_child(UIKit.wrapped_label("星穹列车沿着航线依次停靠。攒够燃料即可启航前往下一站。", UIKit.FONT_SMALL, UIKit.COLOR_MUTED))

	for i in GameData.planets.size():
		var planet: Dictionary = GameData.planets[i]
		if i > 0:
			var link := UIKit.label("│", 44, UIKit.COLOR_MUTED)
			link.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
			link.add_theme_constant_override("outline_size", 0)
			var link_row := UIKit.hbox(0)
			link_row.add_child(UIKit.spacer(Vector2(70, 0), false))
			link_row.add_child(link)
			_list.add_child(link_row)

		var card := UIKit.card()
		var row := UIKit.hbox(24)
		card.add_child(row)
		row.add_child(UIKit.swatch(UIKit.color_from_hex(planet.get("color", "#fff")), 140))

		var info := UIKit.vbox(8)
		info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(info)
		var head := UIKit.hbox(16)
		head.add_child(UIKit.label("%d." % (i + 1), 40, UIKit.COLOR_MUTED))
		head.add_child(UIKit.label(planet.get("name", ""), 44))
		head.add_child(UIKit.spacer())
		var status := UIKit.label("", UIKit.FONT_SMALL, UIKit.COLOR_GOLD)
		head.add_child(status)
		info.add_child(head)
		info.add_child(UIKit.wrapped_label(planet.get("desc", ""), UIKit.FONT_TINY, UIKit.COLOR_MUTED))

		var cost := float(planet.get("fuel_cost", 0.0))
		var cost_text := "起点" if i == 0 else "启航所需燃料：%s" % NumberFormat.format(cost)
		info.add_child(UIKit.label(cost_text, UIKit.FONT_SMALL, UIKit.COLOR_TEXT))

		var unlock := UIKit.wrapped_label(_unlock_text(planet), UIKit.FONT_TINY, UIKit.COLOR_GOOD)
		info.add_child(unlock)

		var bar := UIKit.progress_bar(24)
		bar.visible = false
		info.add_child(bar)

		_list.add_child(card)
		_cards.append({"panel": card, "status": status, "bar": bar, "unlock": unlock, "index": i})


func _unlock_text(planet: Dictionary) -> String:
	var unlocks: Dictionary = planet.get("unlocks", {})
	var parts: Array[String] = []
	for car_id in unlocks.get("cars", []):
		parts.append(GameData.get_car(car_id).get("name", car_id))
	for char_id in unlocks.get("characters", []):
		parts.append(GameData.get_character(char_id).get("name", char_id))
	var slots := int(unlocks.get("dispatch_slots", 0))
	if slots > 0:
		parts.append("派遣槽位 ×%d" % slots)
	if parts.is_empty():
		return ""
	return "解锁：" + "、".join(parts)


func refresh() -> void:
	if not is_node_ready():
		return
	var current: int = GameState.planet_index
	var target: int = int(GameState.travel.get("target", current)) if GameState.is_traveling() else -1
	for card in _cards:
		var i: int = card["index"]
		var status: Label = card["status"]
		var panel: PanelContainer = card["panel"]
		var bar: ProgressBar = card["bar"]
		bar.visible = false
		if i == target:
			status.text = "航行中 →"
			status.add_theme_color_override("font_color", UIKit.COLOR_GOLD)
			bar.visible = true
			panel.modulate = Color(1, 1, 1, 1)
		elif i == current:
			status.text = "● 当前位置"
			status.add_theme_color_override("font_color", UIKit.COLOR_GOOD)
			panel.modulate = Color(1, 1, 1, 1)
		elif i < current:
			status.text = "已抵达"
			status.add_theme_color_override("font_color", UIKit.COLOR_MUTED)
			panel.modulate = Color(0.85, 0.85, 0.85, 1)
		elif i == current + 1:
			status.text = "下一站"
			status.add_theme_color_override("font_color", UIKit.COLOR_GOLD)
			bar.visible = true
			panel.modulate = Color(1, 1, 1, 1)
		else:
			status.text = "未解锁"
			status.add_theme_color_override("font_color", UIKit.COLOR_MUTED)
			panel.modulate = Color(0.6, 0.6, 0.6, 1)
	_refresh_bars()


func _refresh_bars() -> void:
	if not visible or not is_node_ready():
		return
	var current: int = GameState.planet_index
	for card in _cards:
		var bar: ProgressBar = card["bar"]
		if not bar.visible:
			continue
		var i: int = card["index"]
		if GameState.is_traveling() and i == int(GameState.travel.get("target", -1)):
			bar.value = GameState.travel_progress()
		elif i == current + 1:
			var cost := float(GameData.planets[i].get("fuel_cost", 1.0))
			bar.value = clampf(float(GameState.resources.get("fuel", 0.0)) / maxf(cost, 1.0), 0.0, 1.0)
