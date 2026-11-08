class_name UIKit
## 用代码构建占位 UI 的小工具。所有触控元素高度不小于 TOUCH_MIN（44pt @3x）。

const TOUCH_MIN := 132.0

const COLOR_TEXT := Color(0.945, 0.918, 0.84)
const COLOR_MUTED := Color(0.604, 0.655, 0.78)
const COLOR_GOLD := Color(0.85, 0.705, 0.357)
const COLOR_GOOD := Color(0.5, 0.84, 0.54)
const COLOR_BAD := Color(0.94, 0.42, 0.42)
const COLOR_BG := Color(0.039, 0.055, 0.137)

const FONT_TITLE := 56
const FONT_BODY := 40
const FONT_SMALL := 32
const FONT_TINY := 28


static func label(text: String, size: int = FONT_BODY, color: Color = COLOR_TEXT) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


static func wrapped_label(text: String, size: int = FONT_BODY, color: Color = COLOR_TEXT) -> Label:
	var l := label(text, size, color)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l


static func title(text: String) -> Label:
	var l := label(text, FONT_TITLE, COLOR_GOLD)
	return l


static func button(text: String, variation: StringName = &"", min_width: float = 0.0) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(min_width, TOUCH_MIN)
	if variation != &"":
		b.theme_type_variation = variation
	return b


static func vbox(separation: int = 20) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", separation)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return v


static func hbox(separation: int = 20) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", separation)
	h.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return h


static func spacer(min_size: Vector2 = Vector2.ZERO, expand: bool = true) -> Control:
	var c := Control.new()
	c.custom_minimum_size = min_size
	if expand:
		c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return c


static func card() -> PanelContainer:
	var p := PanelContainer.new()
	p.theme_type_variation = &"Card"
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return p


## 彩色圆点 / 色块占位图标。
static func swatch(color: Color, size: float = 96.0, radius: float = -1.0) -> Panel:
	var p := Panel.new()
	p.custom_minimum_size = Vector2(size, size)
	p.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	var r := int(radius if radius >= 0.0 else size / 2.0)
	sb.set_corner_radius_all(r)
	sb.border_color = color.lightened(0.35)
	sb.set_border_width_all(3)
	p.add_theme_stylebox_override("panel", sb)
	return p


static func progress_bar(height: float = 40.0) -> ProgressBar:
	var pb := ProgressBar.new()
	pb.custom_minimum_size = Vector2(0, height)
	pb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	pb.min_value = 0.0
	pb.max_value = 1.0
	pb.show_percentage = false
	return pb


## 一行“说明文字 + 开/关按钮”的设置项；返回的按钮为 toggle 模式。
static func toggle_row(text: String, on_toggled: Callable) -> Dictionary:
	var row := hbox(24)
	row.custom_minimum_size = Vector2(0, TOUCH_MIN)
	var l := wrapped_label(text, FONT_BODY)
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(l)
	var b := button("关闭", &"SecondaryButton", 220)
	b.toggle_mode = true
	b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	b.toggled.connect(func(on: bool):
		_style_toggle(b, on)
		on_toggled.call(on))
	row.add_child(b)
	return {"row": row, "button": b}


static func set_toggle(b: Button, on: bool) -> void:
	b.set_pressed_no_signal(on)
	_style_toggle(b, on)


static func _style_toggle(b: Button, on: bool) -> void:
	b.text = "开启" if on else "关闭"
	b.theme_type_variation = &"" if on else &"SecondaryButton"


static func separator() -> HSeparator:
	var s := HSeparator.new()
	s.add_theme_constant_override("separation", 24)
	return s


static func color_from_hex(hex: String, fallback: Color = COLOR_GOLD) -> Color:
	if Color.html_is_valid(hex):
		return Color.html(hex)
	return fallback


static func clear_children(node: Node) -> void:
	for child in node.get_children():
		node.remove_child(child)
		child.queue_free()
