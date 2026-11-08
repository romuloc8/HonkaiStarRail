extends Node
## 数据加载器：把 data/*.json 读入内存，供 Economy / GameState / UI 查询。
## 所有数值配置都在 JSON 里，代码不写死数字。

const DATA_DIR := "res://data/"

var config: Dictionary = {}
var cars: Array = []
var characters: Array = []
var planets: Array = []
var events: Array = []

var _cars_by_id: Dictionary = {}
var _characters_by_id: Dictionary = {}
var _planets_by_id: Dictionary = {}
var _events_by_id: Dictionary = {}
var _durations_by_id: Dictionary = {}


func _init() -> void:
	load_all()


func load_all() -> void:
	config = _load_json(DATA_DIR + "config.json", {})
	cars = _load_json(DATA_DIR + "cars.json", [])
	characters = _load_json(DATA_DIR + "characters.json", [])
	planets = _load_json(DATA_DIR + "planets.json", [])
	events = _load_json(DATA_DIR + "events.json", [])

	_cars_by_id = _index(cars)
	_characters_by_id = _index(characters)
	_planets_by_id = _index(planets)
	_events_by_id = _index(events)
	_durations_by_id = _index(config.get("dispatch", {}).get("durations", []))


static func _load_json(path: String, fallback: Variant) -> Variant:
	if not FileAccess.file_exists(path):
		push_error("GameData: 找不到数据文件 %s" % path)
		return fallback
	var text := FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null:
		push_error("GameData: 解析 JSON 失败 %s" % path)
		return fallback
	return parsed


static func _index(list: Array) -> Dictionary:
	var out := {}
	for item in list:
		if item is Dictionary and item.has("id"):
			out[item["id"]] = item
	return out


func get_car(id: String) -> Dictionary:
	return _cars_by_id.get(id, {})


func get_character(id: String) -> Dictionary:
	return _characters_by_id.get(id, {})


func get_planet(id: String) -> Dictionary:
	return _planets_by_id.get(id, {})


func get_planet_at(index: int) -> Dictionary:
	if index < 0 or index >= planets.size():
		return {}
	return planets[index]


func get_event(id: String) -> Dictionary:
	return _events_by_id.get(id, {})


func get_duration(id: String) -> Dictionary:
	return _durations_by_id.get(id, {})


func get_durations() -> Array:
	return config.get("dispatch", {}).get("durations", [])


func get_resources() -> Array:
	return config.get("resources", [])


func resource_name(id: String) -> String:
	for res in get_resources():
		if res.get("id", "") == id:
			return res.get("name", id)
	return id


## 返回解锁某节车厢 / 某个角色的星球序号，找不到返回 -1。
func unlock_planet_index(kind: String, id: String) -> int:
	for i in planets.size():
		var unlocks: Dictionary = planets[i].get("unlocks", {})
		if id in unlocks.get(kind, []):
			return i
	return -1
