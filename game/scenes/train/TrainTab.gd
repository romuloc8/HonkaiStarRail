extends Control
## 列车主页：当前星球、航行进度、列车动画、启航按钮、三节车厢卡片。

const CarCardScript := preload("res://scenes/components/CarCard.gd")
const TrainViewScript := preload("res://scenes/components/TrainView.gd")

@onready var _list: VBoxContainer = $Scroll/Margin/List

var _planet_label: Label
var _planet_desc: Label
var _status_label: Label
var _travel_bar: ProgressBar
var _depart_button: Button
var _depart_hint: Label
var _car_cards: Array = []


func _ready() -> void:
	_build()
	GameState.state_changed.connect(refresh)
	GameState.resources_changed.connect(_refresh_live)
	GameState.travel_started.connect(func(_i): refresh())
	GameState.travel_finished.connect(func(_i): refresh())
	refresh()


func _build() -> void:
	# 星球与航行面板
	var panel := PanelContainer.new()
	var box := UIKit.vbox(16)
	panel.add_child(box)

	var head := UIKit.hbox(16)
	head.add_child(UIKit.label("当前星球", UIKit.FONT_SMALL, UIKit.COLOR_MUTED))
	head.add_child(UIKit.spacer())
	_status_label = UIKit.label("停靠中", UIKit.FONT_SMALL, UIKit.COLOR_GOOD)
	head.add_child(_status_label)
	box.add_child(head)

	_planet_label = UIKit.title("")
	box.add_child(_planet_label)
	_planet_desc = UIKit.wrapped_label("", UIKit.FONT_SMALL, UIKit.COLOR_MUTED)
	box.add_child(_planet_desc)

	var train_view: Control = TrainViewScript.new()
	box.add_child(train_view)

	_travel_bar = UIKit.progress_bar(36)
	box.add_child(_travel_bar)

	_depart_button = UIKit.button("启航")
	_depart_button.pressed.connect(_on_depart)
	box.add_child(_depart_button)
	_depart_hint = UIKit.wrapped_label("", UIKit.FONT_SMALL, UIKit.COLOR_MUTED)
	_depart_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_depart_hint)
	_list.add_child(panel)

	# 车厢
	_list.add_child(UIKit.label("车厢", 48, UIKit.COLOR_GOLD))
	for def in GameData.cars:
		var card: PanelContainer = CarCardScript.new()
		card.setup(def)
		_list.add_child(card)
		_car_cards.append(card)


func refresh() -> void:
	if not is_node_ready():
		return
	var planet: Dictionary = GameState.current_planet()
	var next: Dictionary = GameState.next_planet()
	_planet_label.text = planet.get("name", "")
	_planet_desc.text = planet.get("desc", "")
	if GameState.is_traveling():
		_status_label.text = "航行中 → %s" % GameData.get_planet_at(int(GameState.travel.get("target", 0))).get("name", "")
		_status_label.add_theme_color_override("font_color", UIKit.COLOR_GOLD)
		_depart_button.text = "航行中…"
		_depart_button.disabled = true
	elif next.is_empty():
		_status_label.text = "已抵达终点"
		_status_label.add_theme_color_override("font_color", UIKit.COLOR_GOOD)
		_depart_button.text = "已是最远的星球"
		_depart_button.disabled = true
	else:
		_status_label.text = "停靠中"
		_status_label.add_theme_color_override("font_color", UIKit.COLOR_GOOD)
		_depart_button.text = "启航 → %s（%s 燃料）" % [next.get("name", ""), NumberFormat.format(float(next.get("fuel_cost", 0)))]
	for card in _car_cards:
		card.refresh()
	_refresh_live()


## 每帧随资源变化刷新的轻量部分。
func _refresh_live() -> void:
	if not is_node_ready():
		return
	var next: Dictionary = GameState.next_planet()
	if GameState.is_traveling():
		_travel_bar.value = GameState.travel_progress()
		_depart_hint.text = "预计 %s 后抵达" % NumberFormat.format_duration(GameState.travel_remaining_seconds() / GameState.time_scale())
	elif next.is_empty():
		_travel_bar.value = 1.0
		_depart_hint.text = "更多星球敬请期待。"
	else:
		var cost := float(next.get("fuel_cost", 0.0))
		var fuel := float(GameState.resources.get("fuel", 0.0))
		_travel_bar.value = clampf(fuel / maxf(cost, 1.0), 0.0, 1.0)
		var can := GameState.can_depart()
		_depart_button.disabled = not can
		if can:
			_depart_hint.text = "燃料充足，航行约需 %s" % NumberFormat.format_duration(Economy.travel_seconds(GameState) / GameState.time_scale())
		else:
			var rate := Economy.production_rate(GameState, "fuel") * GameState.time_scale()
			var eta := (cost - fuel) / rate if rate > 0.0 else INF
			_depart_hint.text = "燃料 %s / %s，约 %s 后可启航" % [NumberFormat.format(fuel), NumberFormat.format(cost), NumberFormat.format_duration(eta) if not is_inf(eta) else "—"]
	for card in _car_cards:
		card.refresh_buttons()


func _on_depart() -> void:
	GameState.depart()
	refresh()
