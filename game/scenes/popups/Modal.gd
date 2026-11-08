extends Control
## 通用弹窗：标题 + 正文 + 自定义内容区 + 若干按钮。
## 用法：
##   var m := ModalScene.instantiate().setup("标题", "正文", ["取消", "确定"])
##   m.closed.connect(func(i): ...)
##   popups_layer.add_child(m)

signal closed(index: int)

@onready var _title: Label = $Center/Panel/Margin/VBox/Title
@onready var _body: Label = $Center/Panel/Margin/VBox/Body
@onready var _content: VBoxContainer = $Center/Panel/Margin/VBox/Content
@onready var _buttons: VBoxContainer = $Center/Panel/Margin/VBox/Buttons
@onready var _panel: PanelContainer = $Center/Panel

var _pending_title := ""
var _pending_body := ""
var _pending_buttons: Array = []
var _pending_variations: Array = []
var _pending_content: Array = []
var _closed := false


## buttons: 按钮文字数组；variations: 与 buttons 对应的主题变体（可为空）。
func setup(title: String, body: String, buttons: Array, variations: Array = []) -> Control:
	_pending_title = title
	_pending_body = body
	_pending_buttons = buttons
	_pending_variations = variations
	if is_node_ready():
		_apply()
	return self


## 在正文和按钮之间加入自定义控件。
func add_content(node: Control) -> Control:
	_pending_content.append(node)
	if is_node_ready():
		_content.add_child(node)
	return self


func set_button_enabled(index: int, enabled: bool) -> void:
	if index >= 0 and index < _buttons.get_child_count():
		(_buttons.get_child(index) as Button).disabled = not enabled


func set_button_text(index: int, text: String) -> void:
	if index >= 0 and index < _buttons.get_child_count():
		(_buttons.get_child(index) as Button).text = text


func _ready() -> void:
	_apply()
	for node in _pending_content:
		_content.add_child(node)
	_pending_content.clear()
	# 简单的弹出动画
	_panel.scale = Vector2(0.9, 0.9)
	_panel.modulate.a = 0.0
	var tween := create_tween().set_parallel(true)
	tween.tween_property(_panel, "scale", Vector2.ONE, 0.18).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tween.tween_property(_panel, "modulate:a", 1.0, 0.15)


func _apply() -> void:
	_title.text = _pending_title
	_title.visible = not _pending_title.is_empty()
	_body.text = _pending_body
	_body.visible = not _pending_body.is_empty()
	UIKit.clear_children(_buttons)
	for i in _pending_buttons.size():
		var variation: StringName = &""
		if i < _pending_variations.size():
			variation = _pending_variations[i]
		var b := UIKit.button(String(_pending_buttons[i]), variation)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.pressed.connect(_on_button_pressed.bind(i))
		_buttons.add_child(b)
	_buttons.visible = not _pending_buttons.is_empty()


func _on_button_pressed(index: int) -> void:
	close(index)


func close(index: int = -1) -> void:
	if _closed:
		return
	_closed = true
	closed.emit(index)
	queue_free()
