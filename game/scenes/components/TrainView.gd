extends Control
## 列车占位动画：轨道 + 车头 + 车厢色块。停靠时轻微上下浮动，航行时向右滑动并带星星拖尾。

var _time := 0.0


func _ready() -> void:
	custom_minimum_size = Vector2(0, 240)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _process(delta: float) -> void:
	_time += delta
	queue_redraw()


func _draw() -> void:
	var w := size.x
	var h := size.y
	var traveling: bool = GameState.is_traveling()
	var progress: float = GameState.travel_progress()

	# 轨道
	var track_y := h - 40.0
	draw_line(Vector2(0, track_y), Vector2(w, track_y), Color(0.85, 0.705, 0.357, 0.6), 6.0)
	for i in range(0, int(w), 60):
		var offset := fmod(_time * (260.0 if traveling else 0.0), 60.0)
		var x := float(i) - offset
		draw_line(Vector2(x, track_y - 10), Vector2(x, track_y + 10), Color(0.85, 0.705, 0.357, 0.35), 4.0)

	# 车身位置
	var train_w := 0.0
	var cars: Array = GameData.cars
	var car_w := 150.0
	var gap := 18.0
	var head_w := 170.0
	var unlocked_cars: Array = []
	for car in cars:
		if Economy.is_car_unlocked(GameState, car["id"]):
			unlocked_cars.append(car)
	train_w = head_w + unlocked_cars.size() * (car_w + gap)
	var start_x := (w - train_w) * 0.5
	if traveling:
		start_x = lerpf(-train_w, w, progress)
	var bob := sin(_time * 3.0) * 3.0
	var base_y := track_y - 30.0 + bob

	# 尾部拖尾
	if traveling:
		for i in 6:
			var tx := start_x - 20.0 - i * 28.0
			draw_circle(Vector2(tx, base_y - 50.0 + sin(_time * 8.0 + i) * 6.0), 8.0 - i, Color(0.95, 0.93, 0.85, 0.5 - i * 0.07))

	# 车厢（从后往前）
	var x := start_x
	for i in range(unlocked_cars.size() - 1, -1, -1):
		var car: Dictionary = unlocked_cars[i]
		var color := UIKit.color_from_hex(car.get("color", "#888888"))
		var rect := Rect2(x, base_y - 90.0, car_w, 90.0)
		draw_rect(rect, color, true)
		draw_rect(rect, color.lightened(0.3), false, 3.0)
		# 窗户
		for wnd in 3:
			draw_rect(Rect2(x + 18 + wnd * 42, base_y - 72.0, 28, 26), Color(0.9, 0.95, 1.0, 0.7), true)
		# 车轮
		draw_circle(Vector2(x + 32, base_y + 6), 14.0, Color(0.9, 0.9, 0.9))
		draw_circle(Vector2(x + car_w - 32, base_y + 6), 14.0, Color(0.9, 0.9, 0.9))
		x += car_w + gap

	# 车头
	var head_color := Color(0.85, 0.705, 0.357)
	var head := Rect2(x, base_y - 110.0, head_w, 110.0)
	draw_rect(head, head_color, true)
	draw_rect(head, head_color.lightened(0.3), false, 3.0)
	draw_rect(Rect2(x + head_w - 60, base_y - 90.0, 44, 40), Color(0.9, 0.95, 1.0, 0.85), true)
	draw_circle(Vector2(x + 36, base_y + 6), 16.0, Color(0.9, 0.9, 0.9))
	draw_circle(Vector2(x + head_w - 36, base_y + 6), 16.0, Color(0.9, 0.9, 0.9))
	# 车灯
	var glow := 0.6 + 0.4 * sin(_time * 4.0)
	draw_circle(Vector2(x + head_w + 6, base_y - 40.0), 12.0, Color(1.0, 0.95, 0.7, glow))
