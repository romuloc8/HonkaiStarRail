extends Control
## 主场景：顶部资源栏、四个页面切换、底部 Tab 栏、弹窗队列。

const ModalScene := preload("res://scenes/popups/Modal.tscn")

@onready var _resources_box: HBoxContainer = $SafeArea/Layout/Header/Resources
@onready var _safe_area: MarginContainer = $SafeArea
@onready var _popups: CanvasLayer = $Popups
@onready var _tabs: Array[Control] = [
	$SafeArea/Layout/Content/TrainTab,
	$SafeArea/Layout/Content/CharactersTab,
	$SafeArea/Layout/Content/StarMapTab,
	$SafeArea/Layout/Content/SettingsTab,
]
@onready var _tab_buttons: Array[Button] = [
	$SafeArea/Layout/TabBar/TrainButton,
	$SafeArea/Layout/TabBar/CharactersButton,
	$SafeArea/Layout/TabBar/StarMapButton,
	$SafeArea/Layout/TabBar/SettingsButton,
]

var _resource_labels: Dictionary = {}
var _rate_labels: Dictionary = {}
var _modal_queue: Array[Callable] = []
var _modal_open := false
var _toast: PanelContainer
var _toast_label: Label


func _ready() -> void:
	add_to_group("main")
	_apply_safe_area()
	_build_resource_bar()
	for i in _tab_buttons.size():
		_tab_buttons[i].pressed.connect(_on_tab_pressed.bind(i))
	show_tab(0)

	GameState.resources_changed.connect(_refresh_resources)
	GameState.state_changed.connect(_refresh_resources)
	GameState.event_triggered.connect(_on_event_triggered)
	GameState.travel_finished.connect(_on_travel_finished)
	GameState.travel_started.connect(_on_travel_started)
	_refresh_resources()

	# 启动时：先离线收益，再处理排队的事件。
	if not GameState.pending_offline_report.is_empty():
		var report: Dictionary = GameState.pending_offline_report
		GameState.pending_offline_report = {}
		enqueue_modal(func(): return _make_offline_modal(report))
	for i in GameState.pending_events.size():
		enqueue_modal(_make_event_modal)


# ---------------------------------------------------------------------------
# 布局
# ---------------------------------------------------------------------------

func _apply_safe_area() -> void:
	# 刘海 / Home 指示条：根据系统安全区给四周留白。
	var safe := DisplayServer.get_display_safe_area()
	var win := DisplayServer.window_get_size()
	if safe.size == Vector2i.ZERO or win == Vector2i.ZERO:
		return
	# 桌面端安全区等于整个屏幕而非窗口，因此只取非负值。
	var scale := float(get_viewport_rect().size.y) / float(win.y)
	_safe_area.add_theme_constant_override("margin_top", maxi(0, int(safe.position.y * scale)))
	_safe_area.add_theme_constant_override("margin_left", maxi(0, int(safe.position.x * scale)))
	_safe_area.add_theme_constant_override("margin_right", maxi(0, int((win.x - safe.end.x) * scale)))
	_safe_area.add_theme_constant_override("margin_bottom", maxi(0, int((win.y - safe.end.y) * scale)))


func _build_resource_bar() -> void:
	UIKit.clear_children(_resources_box)
	for res in GameData.get_resources():
		var id: String = res["id"]
		var color := UIKit.color_from_hex(res.get("color", "#ffffff"))
		var item := UIKit.vbox(2)
		item.alignment = BoxContainer.ALIGNMENT_CENTER
		var top := UIKit.hbox(12)
		top.alignment = BoxContainer.ALIGNMENT_CENTER
		top.add_child(UIKit.swatch(color, 36))
		top.add_child(UIKit.label(res["name"], UIKit.FONT_SMALL, UIKit.COLOR_MUTED))
		item.add_child(top)
		var value := UIKit.label("0", 44, color)
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		item.add_child(value)
		var rate := UIKit.label("", UIKit.FONT_TINY, UIKit.COLOR_MUTED)
		rate.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		item.add_child(rate)
		_resources_box.add_child(item)
		_resource_labels[id] = value
		_rate_labels[id] = rate


func _refresh_resources() -> void:
	var rates := Economy.production_rates(GameState)
	for id in _resource_labels.keys():
		(_resource_labels[id] as Label).text = NumberFormat.format(float(GameState.resources.get(id, 0.0)))
		var rate := float(rates.get(id, 0.0))
		var rate_label := _rate_labels[id] as Label
		if rate > 0.0:
			rate_label.text = "+" + NumberFormat.format_rate(rate * GameState.time_scale())
		else:
			rate_label.text = "派遣获得" if id == "material" else ""


func _on_tab_pressed(index: int) -> void:
	show_tab(index)


func show_tab(index: int) -> void:
	for i in _tabs.size():
		_tabs[i].visible = (i == index)
		_tab_buttons[i].set_pressed_no_signal(i == index)
		if i == index and _tabs[i].has_method("refresh"):
			_tabs[i].call("refresh")


# ---------------------------------------------------------------------------
# 弹窗队列
# ---------------------------------------------------------------------------

## factory 返回一个 Modal 实例；同一时刻只显示一个弹窗。
func enqueue_modal(factory: Callable) -> void:
	_modal_queue.append(factory)
	_show_next_modal()


func _show_next_modal() -> void:
	if _modal_open or _modal_queue.is_empty():
		return
	var factory: Callable = _modal_queue.pop_front()
	var modal: Control = factory.call()
	if modal == null:
		_show_next_modal()
		return
	_modal_open = true
	modal.closed.connect(_on_modal_closed, CONNECT_DEFERRED)
	_popups.add_child(modal)


func _on_modal_closed(_index: int) -> void:
	_modal_open = false
	_show_next_modal()


## 通用确认框。
func confirm(title: String, body: String, on_confirm: Callable, confirm_text: String = "确定", danger: bool = false) -> void:
	enqueue_modal(func():
		var m: Control = ModalScene.instantiate()
		var variation: StringName = &"DangerButton" if danger else &""
		m.setup(title, body, ["取消", confirm_text], [&"SecondaryButton", variation])
		m.closed.connect(func(i):
			if i == 1:
				on_confirm.call())
		return m)


## 顶部短暂提示。
func toast(text: String) -> void:
	if _toast == null or not is_instance_valid(_toast):
		_toast = PanelContainer.new()
		_toast.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var sb := StyleBoxFlat.new()
		sb.bg_color = Color(0.05, 0.07, 0.16, 0.92)
		sb.border_color = UIKit.COLOR_GOLD
		sb.set_border_width_all(2)
		sb.set_corner_radius_all(32)
		sb.content_margin_left = 40
		sb.content_margin_right = 40
		sb.content_margin_top = 20
		sb.content_margin_bottom = 20
		_toast.add_theme_stylebox_override("panel", sb)
		_toast_label = UIKit.label("", UIKit.FONT_SMALL, UIKit.COLOR_GOLD)
		_toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		_toast_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_toast.add_child(_toast_label)
		_popups.add_child(_toast)
	_toast_label.text = text
	# 贴在底部 Tab 栏上方居中
	_toast.reset_size()
	var viewport_size := get_viewport_rect().size
	var toast_size := _toast.get_combined_minimum_size()
	_toast.position = Vector2((viewport_size.x - toast_size.x) * 0.5, viewport_size.y - 150.0 - toast_size.y - 32.0)
	_toast.modulate.a = 1.0
	var tween := create_tween()
	tween.tween_interval(1.6)
	tween.tween_property(_toast, "modulate:a", 0.0, 0.5)


# ---------------------------------------------------------------------------
# 具体弹窗
# ---------------------------------------------------------------------------

func _make_offline_modal(report: Dictionary) -> Control:
	var m: Control = ModalScene.instantiate()
	var elapsed := NumberFormat.format_duration(float(report.get("elapsed", 0.0)))
	var body := "离开了 %s" % elapsed
	if report.get("capped", false):
		body += "\n（已达到离线上限 %s）" % NumberFormat.format_duration(float(report.get("cap", 0.0)))
	m.setup("离线收益", body, ["领取"])

	var list := UIKit.vbox(12)
	var gains: Dictionary = report.get("gains", {})
	for res in GameData.get_resources():
		var id: String = res["id"]
		var amount := float(gains.get(id, 0.0))
		if amount <= 0.0:
			continue
		var row := UIKit.hbox(16)
		row.add_child(UIKit.swatch(UIKit.color_from_hex(res.get("color", "#fff")), 40))
		row.add_child(UIKit.label(res["name"], UIKit.FONT_BODY, UIKit.COLOR_MUTED))
		row.add_child(UIKit.spacer())
		row.add_child(UIKit.label("+" + NumberFormat.format(amount), UIKit.FONT_BODY, UIKit.COLOR_GOOD))
		list.add_child(row)
	var completed := int(report.get("dispatches_completed", 0))
	if completed > 0:
		list.add_child(UIKit.label("派遣任务完成 %d 个，记得去「角色」页收取。" % completed, UIKit.FONT_SMALL, UIKit.COLOR_GOLD))
	if report.get("arrived", false):
		list.add_child(UIKit.label("列车已抵达 %s。" % GameState.current_planet().get("name", ""), UIKit.FONT_SMALL, UIKit.COLOR_GOLD))
	if list.get_child_count() == 0:
		list.add_child(UIKit.label("列车静静地停着，什么也没发生。", UIKit.FONT_SMALL, UIKit.COLOR_MUTED))
	m.add_content(list)
	return m


func _make_event_modal() -> Control:
	var ev := GameState.current_pending_event()
	if ev.is_empty():
		return null
	var m: Control = ModalScene.instantiate()
	var options: Array = ev.get("options", [])
	var texts: Array = []
	var variations: Array = []
	for opt in options:
		var desc: String = GameState.describe_effects(opt.get("effects", []))
		texts.append("%s\n（%s）" % [opt.get("text", ""), desc])
		variations.append(&"SecondaryButton")
	m.setup(ev.get("title", "事件"), ev.get("text", ""), texts, variations)
	m.closed.connect(func(i):
		var changes: Dictionary = GameState.resolve_event(maxi(i, 0))
		var parts: Array[String] = []
		for id in changes.keys():
			var delta := float(changes[id])
			parts.append("%s %s%s" % [GameData.resource_name(id), "+" if delta >= 0 else "", NumberFormat.format(delta)])
		if not parts.is_empty():
			toast("、".join(parts)))
	return m


func _on_event_triggered(_event: Dictionary) -> void:
	enqueue_modal(_make_event_modal)


func _on_travel_started(target_index: int) -> void:
	var planet := GameData.get_planet_at(target_index)
	toast("启航，前往 %s" % planet.get("name", ""))


func _on_travel_finished(planet_index: int) -> void:
	var planet := GameData.get_planet_at(planet_index)
	toast("抵达 %s" % planet.get("name", ""))
