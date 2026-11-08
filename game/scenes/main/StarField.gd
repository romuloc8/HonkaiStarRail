extends Control
## 背景星空占位：随机小圆点，缓慢闪烁。

const STAR_COUNT := 90

var _stars: Array = []
var _time := 0.0


func _ready() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	for i in STAR_COUNT:
		_stars.append({
			"pos": Vector2(rng.randf(), rng.randf()),
			"radius": rng.randf_range(1.5, 4.5),
			"phase": rng.randf_range(0.0, TAU),
			"speed": rng.randf_range(0.4, 1.4),
		})
	resized.connect(queue_redraw)


func _process(delta: float) -> void:
	_time += delta
	queue_redraw()


func _draw() -> void:
	var s := size
	for star in _stars:
		var alpha: float = 0.35 + 0.35 * sin(_time * star["speed"] + star["phase"])
		draw_circle(star["pos"] * s, star["radius"], Color(0.95, 0.93, 0.85, alpha))
