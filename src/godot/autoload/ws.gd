## WebSocket client singleton.
## Autoloaded as "WS" — available from any script via WS.send(), WS.connected, etc.
extends Node

# ── Signals ────────────────────────────────────────────────────────
signal connected
signal disconnected
signal message_received(data: Dictionary)
signal state_changed(state: String)

# ── Config ─────────────────────────────────────────────────────────
@export var server_url: String = "ws://127.0.0.1:7337/ws/chat"
@export var reconnect_interval: float = 3.0
@export var session_id: String = "godot:main"

# ── Internal ───────────────────────────────────────────────────────
var _socket := WebSocketPeer.new()
var _connected := false
var _reconnect_timer: float = 0.0
var _pending_messages: Array[Dictionary] = []

# ── Lifecycle ──────────────────────────────────────────────────────

func _ready() -> void:
	connect_to_server()


func _process(delta: float) -> void:
	_socket.poll()

	var state = _socket.get_ready_state()

	if state == WebSocketPeer.STATE_OPEN:
		if not _connected:
			_connected = true
			connected.emit()
			_flush_pending()

		while _socket.get_available_packet_count():
			var packet = _socket.get_packet()
			if _socket.was_string_packet():
				_handle_message(packet.get_string_from_utf8())

	elif state == WebSocketPeer.STATE_CLOSING:
		pass  # Keep polling for clean close

	elif state == WebSocketPeer.STATE_CLOSED:
		if _connected:
			_connected = false
			disconnected.emit()
		_reconnect_timer += delta
		if _reconnect_timer >= reconnect_interval:
			_reconnect_timer = 0.0
			connect_to_server()


# ── Public API ─────────────────────────────────────────────────────

func connect_to_server(url: String = "") -> void:
	if url:
		server_url = url
	var err = _socket.connect_to_url(server_url)
	if err != OK:
		push_error("[WS] Connection failed: %s" % error_string(err))
	_reconnect_timer = 0.0


func send(data: Dictionary) -> void:
	if _connected:
		_socket.send_text(JSON.stringify(data))
	else:
		_pending_messages.append(data)


func send_chat(message: String) -> void:
	send({"type": "chat", "message": message, "session_id": session_id})


func request_config() -> void:
	send({"type": "config"})


func request_status() -> void:
	send({"type": "status"})


func is_connected_to_server() -> bool:
	return _connected


# ── Internal ───────────────────────────────────────────────────────

func _handle_message(text: String) -> void:
	var json = JSON.new()
	var error = json.parse(text)
	if error != OK:
		push_warning("[WS] JSON parse error: %s" % json.get_error_message())
		return

	var data = json.data
	if not data is Dictionary:
		push_warning("[WS] Expected Dictionary, got: %s" % typeof(data))
		return

	var msg_type = data.get("type", "")

	match msg_type:
		"token":
			message_received.emit(data)
		"tool_start":
			message_received.emit(data)
		"tool_done":
			message_received.emit(data)
		"done":
			message_received.emit(data)
		"error":
			message_received.emit(data)
		"state":
			var state = data.get("state", "idle")
			state_changed.emit(state)
			message_received.emit(data)
		"config":
			message_received.emit(data)
		"status":
			message_received.emit(data)
		_:
			message_received.emit(data)


func _flush_pending() -> void:
	for msg in _pending_messages:
		_socket.send_text(JSON.stringify(msg))
	_pending_messages.clear()


func _exit_tree() -> void:
	_socket.close()
