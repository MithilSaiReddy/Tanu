## Main scene controller.
## Handles user input, WebSocket communication, and UI.
extends Control

# ── Node references ────────────────────────────────────────────────
@onready var character: Node2D = $Character
@onready var status_label: Label = $UI/VBox/TopBar/StatusLabel
@onready var input_field: LineEdit = $UI/VBox/InputRow/InputField
@onready var send_button: Button = $UI/VBox/InputRow/SendButton
@onready var response_label: RichTextLabel = $UI/VBox/ResponseLabel
@onready var connection_dot: ColorRect = $UI/VBox/TopBar/ConnectionDot

# ── State ──────────────────────────────────────────────────────────
var _is_generating: bool = false
var _current_response: String = ""

# ── Lifecycle ──────────────────────────────────────────────────────

func _ready() -> void:
	# Connect UI signals
	send_button.pressed.connect(_on_send_pressed)
	input_field.text_submitted.connect(_on_text_submitted)

	# WebSocket signals
	WS.connected.connect(_on_ws_connected)
	WS.disconnected.connect(_on_ws_disconnected)
	WS.message_received.connect(_on_ws_message)

	# Initial state
	_update_connection_indicator(false)
	status_label.text = "Connecting..."


func _input(event: InputEvent) -> void:
	# Hotkey: Ctrl+Enter to send
	if event is InputEventKey:
		if event.pressed and event.keycode == KEY_ENTER and event.ctrl_pressed:
			_on_send_pressed()


# ── UI Actions ─────────────────────────────────────────────────────

func _on_send_pressed() -> void:
	var text = input_field.text.strip_edges()
	if text.is_empty() or _is_generating:
		print("[MAIN] Ignored send: empty=%s generating=%s" % [text.is_empty(), _is_generating])
		return

	print("[MAIN] Sending: %s" % text)
	input_field.text = ""
	_current_response = ""
	response_label.text = ""
	_is_generating = true

	WS.send_chat(text)
	status_label.text = "Thinking..."


func _on_text_submitted(text: String) -> void:
	_on_send_pressed()


# ── WebSocket handlers ─────────────────────────────────────────────

func _on_ws_connected() -> void:
	_update_connection_indicator(true)
	status_label.text = "Ready"
	WS.request_status()


func _on_ws_disconnected() -> void:
	_update_connection_indicator(false)
	status_label.text = "Disconnected — reconnecting..."


func _on_ws_message(data: Dictionary) -> void:
	var msg_type = data.get("type", "")
	print("[MAIN] WS msg: type=%s" % msg_type)

	match msg_type:
		"token":
			var token = data.get("content", "")
			_current_response += token
			response_label.text = _current_response
			status_label.text = "Speaking..."

		"tool_start":
			var tool_name = data.get("name", "")
			status_label.text = "Using: %s..." % tool_name

		"tool_done":
			status_label.text = "Thinking..."

		"response":
			_current_response = data.get("content", "")
			response_label.text = _current_response

		"done":
			_is_generating = false
			status_label.text = "Ready"

		"error":
			_is_generating = false
			var err = data.get("message", data.get("content", "Unknown error"))
			response_label.text = "[color=red]Error: %s[/color]" % err
			status_label.text = "Error"

		"state":
			var state = data.get("state", "idle")
			match state:
				"thinking":
					status_label.text = "Thinking..."
				"speaking":
					status_label.text = "Speaking..."
				"idle":
					status_label.text = "Ready"

		"status":
			var provider = data.get("provider", "")
			var model = data.get("model", "")
			if provider:
				status_label.text = "%s / %s" % [provider, model]

		"config":
			pass  # Could update settings UI here


func _update_connection_indicator(connected: bool) -> void:
	if connected:
		connection_dot.color = Color("#00ff88")
	else:
		connection_dot.color = Color("#ff4444")
