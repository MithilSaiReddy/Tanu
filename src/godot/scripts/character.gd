## Character face state machine.
## Controls the visual representation of Tanu based on agent state.
extends Node2D

# ── States ─────────────────────────────────────────────────────────
enum State { IDLE, LISTENING, THINKING, SPEAKING, ERROR }

var _current_state: State = State.IDLE
var _animation_time: float = 0.0
var _response_text: String = ""
var _current_token: String = ""

# ── Visual config ──────────────────────────────────────────────────
@export var face_radius: float = 80.0
@export var face_color: Color = Color("#1a1a2e")
@export var accent_color: Color = Color("#00d4ff")
@export var glow_color: Color = Color("#00d4ff", 0.3)

# ── Colors per state ──────────────────────────────────────────────
var _state_colors: Dictionary = {
	State.IDLE:      Color("#00d4ff"),
	State.LISTENING: Color("#00ff88"),
	State.THINKING:  Color("#ffaa00"),
	State.SPEAKING:  Color("#ff00ff"),
	State.ERROR:     Color("#ff4444"),
}

# ── Lifecycle ──────────────────────────────────────────────────────

func _ready() -> void:
	# Connect to WebSocket signals
	WS.state_changed.connect(_on_state_changed)
	WS.message_received.connect(_on_message)
	WS.connected.connect(_on_connected)
	WS.disconnected.connect(_on_disconnected)


func _process(delta: float) -> void:
	_animation_time += delta
	queue_redraw()


func _draw() -> void:
	var center = Vector2(get_viewport_rect().size.x / 2, get_viewport_rect().size.y / 2)
	var color = _state_colors.get(_current_state, accent_color)

	# Outer glow
	var glow_alpha = 0.2 + 0.1 * sin(_animation_time * 2.0)
	draw_circle(center, face_radius + 20, Color(color, glow_alpha))

	# Main face circle
	draw_circle(center, face_radius, face_color)

	# State-specific animation
	match _current_state:
		State.IDLE:
			_draw_idle(center, color)
		State.LISTENING:
			_draw_listening(center, color)
		State.THINKING:
			_draw_thinking(center, color)
		State.SPEAKING:
			_draw_speaking(center, color)
		State.ERROR:
			_draw_error(center, color)


# ── Drawing functions ──────────────────────────────────────────────

func _draw_idle(center: Vector2, color: Color) -> void:
	# Gentle breathing animation
	var breathe = sin(_animation_time * 1.5) * 3
	draw_circle(center, 4 + breathe, color)

	# Subtle orbit dots
	for i in range(3):
		var angle = _animation_time * 0.5 + i * TAU / 3
		var orbit_pos = center + Vector2(cos(angle), sin(angle)) * (face_radius * 0.6)
		draw_circle(orbit_pos, 2, Color(color, 0.4))


func _draw_listening(center: Vector2, color: Color) -> void:
	# Pulsing rings
	for i in range(3):
		var ring_radius = face_radius * 0.4 + i * 15
		var alpha = 0.6 - i * 0.15
		var pulse = sin(_animation_time * 4.0 + i) * 5
		draw_arc(center, ring_radius + pulse, 0, TAU, 64, Color(color, alpha), 2.0)

	# Center dot
	draw_circle(center, 6, color)


func _draw_thinking(center: Vector2, color: Color) -> void:
	# Spinning dots
	for i in range(5):
		var angle = _animation_time * 3.0 + i * TAU / 5
		var r = face_radius * 0.5
		var pos = center + Vector2(cos(angle), sin(angle)) * r
		var dot_size = 3 + sin(_animation_time * 5 + i) * 1.5
		draw_circle(pos, dot_size, Color(color, 0.7))

	# Center question mark (text)
	# Using a simple circle pattern instead of text for now
	draw_circle(center, 5, Color(color, 0.5 + sin(_animation_time * 4) * 0.3))


func _draw_speaking(center: Vector2, color: Color) -> void:
	# Sound wave bars
	var bar_count = 8
	var bar_width = 6.0
	var max_height = face_radius * 0.6

	for i in range(bar_count):
		var angle = (i - bar_count / 2.0) * 0.2
		var x = center.x + angle * (face_radius * 0.8)
		var height = max_height * (0.3 + 0.7 * abs(sin(_animation_time * 8.0 + i * 0.7)))
		var bar_color = Color(color, 0.6 + 0.4 * sin(_animation_time * 3 + i))

		draw_rect(
			Rect2(x - bar_width / 2, center.y - height / 2, bar_width, height),
			bar_color
		)


func _draw_error(center: Vector2, color: Color) -> void:
	# Flashing X
	var flash = sin(_animation_time * 6.0) > 0
	if flash:
		var s = 15.0
		draw_line(center + Vector2(-s, -s), center + Vector2(s, s), color, 3.0)
		draw_line(center + Vector2(s, -s), center + Vector2(-s, s), color, 3.0)


# ── Signal handlers ────────────────────────────────────────────────

func _on_state_changed(state: String) -> void:
	match state:
		"idle":
			_current_state = State.IDLE
		"listening":
			_current_state = State.LISTENING
		"thinking":
			_current_state = State.THINKING
		"speaking":
			_current_state = State.SPEAKING
		"error":
			_current_state = State.ERROR


func _on_message(data: Dictionary) -> void:
	var msg_type = data.get("type", "")
	match msg_type:
		"token":
			_current_state = State.SPEAKING
			_current_token = data.get("content", "")
		"tool_start":
			_current_state = State.THINKING
		"done":
			_current_state = State.IDLE
			_response_text = ""
			_current_token = ""
		"error":
			_current_state = State.ERROR


func _on_connected() -> void:
	_current_state = State.IDLE


func _on_disconnected() -> void:
	_current_state = State.ERROR
