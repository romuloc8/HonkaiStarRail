extends Control
## 角色页：派遣槽位、已招募 / 可招募角色列表。

const CharacterCardScript := preload("res://scenes/components/CharacterCard.gd")
const DispatchSlotScript := preload("res://scenes/components/DispatchSlot.gd")
const ModalScene := preload("res://scenes/popups/Modal.tscn")

@onready var _list: VBoxContainer = $Scroll/Margin/List

var _slots_box: VBoxContainer
var _slot_hint: Label
var _slot_cards: Array = []
var _char_cards: Array = []


func _ready() -> void:
	_build()
	GameState.state_changed.connect(refresh)
	GameState.dispatch_changed.connect(_refresh_slots)
	GameState.resources_changed.connect(_refresh_buttons)
	refresh()


func _build() -> void:
	_list.add_child(UIKit.label("派遣任务", 48, UIKit.COLOR_GOLD))
	_slots_box = UIKit.vbox(20)
	_list.add_child(_slots_box)
	_slot_hint = UIKit.wrapped_label("", UIKit.FONT_SMALL, UIKit.COLOR_MUTED)
	_list.add_child(_slot_hint)

	_list.add_child(UIKit.label("角色", 48, UIKit.COLOR_GOLD))
	for def in GameData.characters:
		var card: PanelContainer = CharacterCardScript.new()
		card.setup(def)
		_list.add_child(card)
		_char_cards.append(card)


func refresh() -> void:
	if not is_node_ready():
		return
	_rebuild_slots()
	for card in _char_cards:
		card.refresh()


func _rebuild_slots() -> void:
	var count: int = GameState.dispatch_slot_count()
	if _slot_cards.size() != count:
		UIKit.clear_children(_slots_box)
		_slot_cards.clear()
		for i in count:
			var slot_card: PanelContainer = DispatchSlotScript.new()
			slot_card.setup(i)
			slot_card.dispatch_requested.connect(_open_dispatch_dialog)
			_slots_box.add_child(slot_card)
			_slot_cards.append(slot_card)
	# 下一个槽位的解锁提示
	var hint := ""
	for i in range(GameState.planet_index + 1, GameData.planets.size()):
		var p: Dictionary = GameData.planets[i]
		if int(p.get("unlocks", {}).get("dispatch_slots", 0)) > 0:
			hint = "抵达 %s 后解锁更多派遣槽位。" % p.get("name", "")
			break
	_slot_hint.text = hint
	_slot_hint.visible = not hint.is_empty()
	_refresh_slots()


func _refresh_slots() -> void:
	for slot_card in _slot_cards:
		slot_card.refresh()


func _refresh_buttons() -> void:
	if not visible:
		return
	for card in _char_cards:
		card.refresh_buttons()
	for slot_card in _slot_cards:
		slot_card.refresh()


# ---------------------------------------------------------------------------
# 派遣选择弹窗
# ---------------------------------------------------------------------------

func _open_dispatch_dialog(slot: int) -> void:
	var main := get_tree().get_first_node_in_group("main")
	if main == null or not main.has_method("enqueue_modal"):
		return
	main.call("enqueue_modal", func(): return _make_dispatch_modal(slot))


func _make_dispatch_modal(slot: int) -> Control:
	var idle: Array = GameState.idle_characters()
	if idle.is_empty() or not GameState.get_dispatch(slot).is_empty():
		return null
	var m: Control = ModalScene.instantiate()
	m.setup("派遣 · 槽位 %d" % (slot + 1), "选择角色与任务时长。时长越长，素材越多。", ["取消", "出发"], [&"SecondaryButton", &""])

	var selected := {"char_id": "", "duration_id": ""}
	var content := UIKit.vbox(16)

	content.add_child(UIKit.label("角色", UIKit.FONT_SMALL, UIKit.COLOR_MUTED))
	var char_group := ButtonGroup.new()
	var char_row := UIKit.hbox(16)
	for id in idle:
		var def: Dictionary = GameData.get_character(id)
		var b := UIKit.button(def.get("name", id), &"SecondaryButton")
		b.toggle_mode = true
		b.button_group = char_group
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.pressed.connect(func():
			selected["char_id"] = id
			_update_dispatch_modal(m, selected))
		char_row.add_child(b)
	content.add_child(char_row)

	content.add_child(UIKit.label("时长", UIKit.FONT_SMALL, UIKit.COLOR_MUTED))
	var dur_group := ButtonGroup.new()
	var dur_box := UIKit.vbox(12)
	for duration in GameData.get_durations():
		var reward := Economy.dispatch_reward(GameState, duration["id"])
		var b := UIKit.button("%s　→　%s 素材" % [duration.get("name", ""), NumberFormat.format(reward)], &"SecondaryButton")
		b.toggle_mode = true
		b.button_group = dur_group
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.pressed.connect(func():
			selected["duration_id"] = duration["id"]
			_update_dispatch_modal(m, selected))
		dur_box.add_child(b)
	content.add_child(dur_box)
	m.add_content(content)

	m.ready.connect(func(): _update_dispatch_modal(m, selected))
	m.closed.connect(func(i):
		if i == 1 and selected["char_id"] != "" and selected["duration_id"] != "":
			GameState.start_dispatch(slot, selected["char_id"], selected["duration_id"])
			refresh())
	return m


func _update_dispatch_modal(m: Control, selected: Dictionary) -> void:
	m.set_button_enabled(1, selected["char_id"] != "" and selected["duration_id"] != "")
