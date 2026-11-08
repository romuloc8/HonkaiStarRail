class_name StateFactory
## 单元测试公用工具：创建一个不自动读档、不随帧推进的 GameState 实例。

const GameStateScript := preload("res://autoload/GameState.gd")
const TEST_SAVE_PATH := "user://test_save.json"


static func make_state(parent: Node) -> Node:
	var gs: Node = GameStateScript.new()
	gs.auto_boot = false
	gs.save_path = TEST_SAVE_PATH
	parent.add_child(gs)
	gs.set_process(false)
	gs.reset_state()
	return gs


static func remove_test_save() -> void:
	if FileAccess.file_exists(TEST_SAVE_PATH):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(TEST_SAVE_PATH))
