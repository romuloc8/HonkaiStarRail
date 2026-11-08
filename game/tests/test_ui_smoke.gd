extends GutTest
## UI 冒烟测试：主场景能加载、页面能切换、弹窗与按钮能驱动 GameState。
## 使用全局 GameState 自动加载（测试模式下不读写真实存档）。

const MainScene := preload("res://scenes/main/Main.tscn")
const UI_SAVE_PATH := "user://test_ui_save.json"

var main: Control


func before_each() -> void:
	GameState.auto_boot = false
	GameState.set_process(false)
	GameState.save_path = UI_SAVE_PATH
	GameState.reset_state()
	GameState.pending_offline_report = {}


func after_each() -> void:
	if is_instance_valid(main):
		main.free()
	if FileAccess.file_exists(UI_SAVE_PATH):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(UI_SAVE_PATH))


func _open_main() -> void:
	main = MainScene.instantiate()
	add_child(main)
	await wait_process_frames(2)


func _popups() -> CanvasLayer:
	return main.get_node("Popups")


func _modal_buttons(modal: Node) -> Array:
	return modal.get_node("Center/Panel/Margin/VBox/Buttons").get_children()


func test_main_scene_loads_with_four_tabs() -> void:
	await _open_main()
	assert_not_null(main)
	var tabs: Array = main._tabs
	assert_eq(tabs.size(), 4)
	assert_true(tabs[0].visible, "默认显示列车页")
	assert_false(tabs[1].visible)
	main._tab_buttons[2].pressed.emit()
	assert_false(tabs[0].visible)
	assert_true(tabs[2].visible, "点击 Tab 切换到星图页")


func test_resource_bar_formats_numbers() -> void:
	await _open_main()
	GameState.resources["jade"] = 1234.0
	GameState.resources_changed.emit()
	var label: Label = main._resource_labels["jade"]
	assert_eq(label.text, "1.2K")


func test_car_card_upgrade_button_spends_jade() -> void:
	await _open_main()
	var train_tab: Control = main._tabs[0]
	var card = train_tab._car_cards[0]
	assert_true(card._upgrade_button.disabled, "没钱时不可升级")
	GameState.resources["jade"] = 1e6
	GameState.resources_changed.emit()
	assert_false(card._upgrade_button.disabled)
	card._upgrade_button.pressed.emit()
	assert_eq(GameState.car_level(card.car_id), 1)


func test_tab_buttons_meet_touch_size() -> void:
	await _open_main()
	for b in main._tab_buttons:
		assert_true(b.size.y >= UIKit.TOUCH_MIN, "Tab 按钮高度 %s ≥ 44pt" % b.size.y)


func test_event_modal_appears_and_resolves() -> void:
	await _open_main()
	GameState.resources["jade"] = 1000.0
	GameState.pending_events.clear()
	GameState.triggered_events = ["pom_pom_audit"]  # 让 pick 跳过它，这里直接手动塞事件
	GameState.pending_events = ["pom_pom_audit"]
	GameState.event_triggered.emit(GameData.get_event("pom_pom_audit"))
	await wait_process_frames(2)
	var popups := _popups()
	assert_eq(popups.get_child_count(), 1, "出现一个事件弹窗")
	var modal: Node = popups.get_child(0)
	var buttons := _modal_buttons(modal)
	assert_eq(buttons.size(), 2, "两个选项")
	(buttons[0] as Button).pressed.emit()
	await wait_process_frames(2)
	assert_eq(GameState.pending_events.size(), 0)
	assert_almost_eq(GameState.resources["jade"], 1050.0, 0.001, "选项一：星琼 +5%")


func test_offline_modal_shown_on_start() -> void:
	GameState.pending_offline_report = {
		"elapsed": 3600.0, "effective": 3600.0, "cap": 28800.0, "capped": false,
		"gains": {"jade": 3600.0, "fuel": 1440.0, "material": 0.0},
		"dispatches_completed": 1, "arrived": false,
	}
	await _open_main()
	var popups := _popups()
	assert_eq(popups.get_child_count(), 1)
	var title: Label = popups.get_child(0).get_node("Center/Panel/Margin/VBox/Title")
	assert_eq(title.text, "离线收益")
	assert_true(GameState.pending_offline_report.is_empty(), "报告被消费")
	(_modal_buttons(popups.get_child(0))[0] as Button).pressed.emit()
	await wait_process_frames(2)
	assert_eq(popups.get_child_count(), 0)


func test_dispatch_dialog_flow() -> void:
	GameState.characters["march7"] = 1
	await _open_main()
	main.show_tab(1)
	var chars_tab: Control = main._tabs[1]
	assert_eq(chars_tab._slot_cards.size(), 1)
	chars_tab._slot_cards[0]._button.pressed.emit()
	await wait_process_frames(2)
	var popups := _popups()
	assert_eq(popups.get_child_count(), 1, "出现派遣弹窗")
	var modal: Node = popups.get_child(0)
	var content: Node = modal.get_node("Center/Panel/Margin/VBox/Content")
	# 内容：角色行 + 时长列表
	var char_buttons: Array = content.get_child(0).get_child(1).get_children()
	var dur_buttons: Array = content.get_child(0).get_child(3).get_children()
	assert_eq(char_buttons.size(), 1)
	assert_eq(dur_buttons.size(), 3)
	var confirm: Button = _modal_buttons(modal)[1]
	assert_true(confirm.disabled, "未选择前不能出发")
	(char_buttons[0] as Button).button_pressed = true
	(char_buttons[0] as Button).pressed.emit()
	(dur_buttons[0] as Button).button_pressed = true
	(dur_buttons[0] as Button).pressed.emit()
	assert_false(confirm.disabled)
	confirm.pressed.emit()
	await wait_process_frames(2)
	assert_true(GameState.is_character_dispatched("march7"))
	assert_eq(GameState.get_dispatch(0)["duration_id"], "short")


func test_settings_debug_toggle() -> void:
	await _open_main()
	main.show_tab(3)
	var settings_tab: Control = main._tabs[3]
	settings_tab._debug_toggle.button_pressed = true
	assert_true(GameState.settings["debug_speed"])
	assert_true(GameState.time_scale() > 1.0)
