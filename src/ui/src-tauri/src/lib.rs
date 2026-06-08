use std::sync::Mutex;
use std::process::{Command, Child, Stdio};
use std::net::TcpStream;
use std::time::Duration;
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, WebviewWindow,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use tauri_plugin_opener::OpenerExt;

const FLOAT_SIZE: (u32, u32) = (60, 60);
const CHAT_SIZE: (u32, u32) = (400, 600);
const CHAT_MAX: (u32, u32) = (900, 1000);
const MARGIN: i32 = 20;

struct AppState {
    is_chat: Mutex<bool>,
    is_visible: Mutex<bool>,
    float_pos: Mutex<Option<(i32, i32)>>,
    chat_pos: Mutex<Option<(i32, i32)>>,
    server_proc: Mutex<Option<Child>>,
}

fn default_float_pos(window: &WebviewWindow) -> (i32, i32) {
    if let Some(m) = window.current_monitor().ok().flatten() {
        let s = m.size();
        (s.width as i32 - FLOAT_SIZE.0 as i32 - MARGIN, s.height as i32 - FLOAT_SIZE.1 as i32 - MARGIN)
    } else {
        (0, 0)
    }
}

fn default_chat_pos(window: &WebviewWindow) -> (i32, i32) {
    if let Some(m) = window.current_monitor().ok().flatten() {
        let s = m.size();
        (s.width as i32 - CHAT_SIZE.0 as i32 - MARGIN, s.height as i32 - CHAT_SIZE.1 as i32 - MARGIN)
    } else {
        (0, 0)
    }
}

const SCREEN_MARGIN: i32 = 10;

fn clamp_to_screen(window: &WebviewWindow) {
    if let Some(m) = window.current_monitor().ok().flatten() {
        let screen = m.size();
        if let Ok(pos) = window.outer_position() {
            let w = window.outer_size().unwrap_or(tauri::PhysicalSize::new(60, 60));
            let x = pos.x.clamp(SCREEN_MARGIN, screen.width as i32 - w.width as i32 - SCREEN_MARGIN);
            let y = pos.y.clamp(SCREEN_MARGIN, screen.height as i32 - w.height as i32 - SCREEN_MARGIN);
            if x != pos.x || y != pos.y {
                let _ = window.set_position(tauri::PhysicalPosition::new(x, y));
            }
        }
    }
}

fn save_current_pos(window: &WebviewWindow, state: &AppState, leaving_chat: bool) {
    if let Ok(pos) = window.outer_position() {
        let mut target = if leaving_chat {
            state.chat_pos.lock().unwrap()
        } else {
            state.float_pos.lock().unwrap()
        };
        *target = Some((pos.x, pos.y));
    }
}

fn switch_to_chat(window: &WebviewWindow, state: &AppState) {
    save_current_pos(window, state, false);

    let (x, y) = state.chat_pos.lock().unwrap()
        .unwrap_or_else(|| default_chat_pos(window));

    let _ = window.set_size(tauri::LogicalSize::new(CHAT_SIZE.0 as f64, CHAT_SIZE.1 as f64));
    let _ = window.set_min_size(Some(tauri::LogicalSize::new(CHAT_SIZE.0 as f64, CHAT_SIZE.1 as f64)));
    let _ = window.set_max_size(Some(tauri::LogicalSize::new(CHAT_MAX.0 as f64, CHAT_MAX.1 as f64)));
    let _ = window.set_position(tauri::LogicalPosition::new(x as f64, y as f64));
    clamp_to_screen(&window);
    let _ = window.set_always_on_top(true);
    let _ = window.set_resizable(true);
    let _ = window.set_focus();
    let _ = window.emit("mode-changed", "chat");
}

fn switch_to_float(window: &WebviewWindow, state: &AppState) {
    save_current_pos(window, state, true);

    let (x, y) = state.float_pos.lock().unwrap()
        .unwrap_or_else(|| default_float_pos(window));

    let _ = window.set_size(tauri::LogicalSize::new(FLOAT_SIZE.0 as f64, FLOAT_SIZE.1 as f64));
    let _ = window.set_min_size(Some(tauri::LogicalSize::new(FLOAT_SIZE.0 as f64, FLOAT_SIZE.1 as f64)));
    let _ = window.set_max_size(Some(tauri::LogicalSize::new(FLOAT_SIZE.0 as f64, FLOAT_SIZE.1 as f64)));
    let _ = window.set_position(tauri::LogicalPosition::new(x as f64, y as f64));
    clamp_to_screen(&window);
    let _ = window.set_always_on_top(true);
    let _ = window.set_resizable(false);
    let _ = window.emit("mode-changed", "floating");
}

fn hide_to_tray(window: &WebviewWindow, state: &AppState) {
    let _ = window.hide();
    *state.is_visible.lock().unwrap() = false;
}

fn show_window(window: &WebviewWindow, state: &AppState) {
    let is_chat = *state.is_chat.lock().unwrap();
    if !is_chat {
        let _ = window.set_size(tauri::LogicalSize::new(FLOAT_SIZE.0 as f64, FLOAT_SIZE.1 as f64));
    }
    let _ = window.show();
    let _ = window.set_focus();
    *state.is_visible.lock().unwrap() = true;
}

#[tauri::command]
async fn toggle_mode(window: WebviewWindow, state: tauri::State<'_, AppState>) -> Result<String, String> {
    if !*state.is_visible.lock().map_err(|e| e.to_string())? {
        show_window(&window, &state);
        return Ok(if *state.is_chat.lock().unwrap() { "chat" } else { "floating" }.to_string());
    }
    let mut is_chat = state.is_chat.lock().map_err(|e| e.to_string())?;
    if *is_chat {
        switch_to_float(&window, &state);
        *is_chat = false;
        Ok("floating".into())
    } else {
        switch_to_chat(&window, &state);
        *is_chat = true;
        Ok("chat".into())
    }
}

#[tauri::command]
async fn set_chat(window: WebviewWindow, state: tauri::State<'_, AppState>) -> Result<String, String> {
    if !*state.is_visible.lock().map_err(|e| e.to_string())? {
        show_window(&window, &state);
    }
    let mut is_chat = state.is_chat.lock().map_err(|e| e.to_string())?;
    if !*is_chat {
        switch_to_chat(&window, &state);
        *is_chat = true;
    }
    Ok("chat".into())
}

#[tauri::command]
async fn set_floating(window: WebviewWindow, state: tauri::State<'_, AppState>) -> Result<String, String> {
    if !*state.is_visible.lock().map_err(|e| e.to_string())? {
        show_window(&window, &state);
    }
    let mut is_chat = state.is_chat.lock().map_err(|e| e.to_string())?;
    if *is_chat {
        switch_to_float(&window, &state);
        *is_chat = false;
    }
    Ok("floating".into())
}

#[tauri::command]
async fn start_native_drag(window: WebviewWindow) -> Result<(), String> {
    window.start_dragging().map_err(|e| e.to_string())?;
    clamp_to_screen(&window);
    Ok(())
}

#[tauri::command]
async fn open_url_in_browser(url: String, app: tauri::AppHandle) -> Result<(), String> {
    app.opener().open_url(&url, None::<&str>).map_err(|e| e.to_string())
}

#[tauri::command]
async fn get_mode(state: tauri::State<'_, AppState>) -> Result<String, String> {
    let is_chat = state.is_chat.lock().map_err(|e| e.to_string())?;
    Ok(if *is_chat { "chat" } else { "floating" }.to_string())
}

#[tauri::command]
async fn hide_app(window: WebviewWindow, state: tauri::State<'_, AppState>) -> Result<(), String> {
    hide_to_tray(&window, &state);
    Ok(())
}

fn start_python_server() -> Option<Child> {
    let python = std::env::var("TANU_PYTHON").unwrap_or_else(|_| "python3".into());

    // If server is already running, skip
    if TcpStream::connect_timeout(
        &"127.0.0.1:7337".parse().unwrap(),
        Duration::from_millis(200),
    )
    .is_ok()
    {
        return None;
    }

    // Locate project root: binary path is src/ui/src-tauri/target/{release,debug}/tanu
    let root = if let Ok(dir) = std::env::var("TANU_ROOT") {
        std::path::PathBuf::from(dir)
    } else if let Ok(exe) = std::env::current_exe() {
        let mut p = exe.parent()?.to_path_buf();
        // walk up to find pyproject.toml
        for _ in 0..10 {
            if p.join("pyproject.toml").exists() || p.join("main.py").exists() {
                break;
            }
            p = p.parent()?.to_path_buf();
        }
        p
    } else {
        return None;
    };

    let child = Command::new(&python)
        .args(["main.py", "serve"])
        .current_dir(&root)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;

    Some(child)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    if event.state == ShortcutState::Pressed
                        && shortcut.matches(Modifiers::CONTROL | Modifiers::SHIFT, Code::KeyT)
                    {
                        if let Some(window) = app.get_webview_window("main") {
                            let state = app.state::<AppState>();
                            if !*state.is_visible.lock().unwrap() {
                                show_window(&window, &state);
                                return;
                            }
                            let mut is_chat = state.is_chat.lock().unwrap();
                            if *is_chat {
                                switch_to_float(&window, &state);
                                *is_chat = false;
                            } else {
                                switch_to_chat(&window, &state);
                                *is_chat = true;
                            }
                        }
                    }
                })
                .build(),
        )
        .manage(AppState {
            is_chat: Mutex::new(false),
            is_visible: Mutex::new(true),
            float_pos: Mutex::new(None),
            chat_pos: Mutex::new(None),
            server_proc: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            toggle_mode, set_chat, set_floating,
            start_native_drag, get_mode, open_url_in_browser,
            hide_app
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();
            let (x, y) = default_float_pos(&window);
            let _ = window.set_position(tauri::LogicalPosition::new(x as f64, y as f64));
            let _ = window.set_resizable(false);
            let _ = app.global_shortcut().register(
                Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyT),
            );

            // Intercept close → hide to tray
            let w = window.clone();
            window.on_window_event(move |event| {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    let state = w.state::<AppState>();
                    hide_to_tray(&w, &state);
                    api.prevent_close();
                }
            });

            // ── Start Python server ──
            if let Some(child) = start_python_server() {
                *app.state::<AppState>().server_proc.lock().unwrap() = Some(child);
            }

            // ── System Tray ──
            let show_item = MenuItemBuilder::with_id("show", "Show Tanu").build(app).unwrap();
            let quit_item = MenuItemBuilder::with_id("quit", "Quit").build(app).unwrap();
            let menu = MenuBuilder::new(app)
                .item(&show_item)
                .item(&quit_item)
                .build()
                .unwrap();

            fn load_tray_icon() -> tauri::image::Image<'static> {
                let bytes = include_bytes!("../icons/tray-icon.png");
                let decoder = png::Decoder::new(std::io::Cursor::new(&bytes[..]));
                let mut reader = decoder.read_info().unwrap();
                let mut rgba = vec![0u8; reader.output_buffer_size().unwrap()];
                reader.next_frame(&mut rgba).unwrap();
                let info = reader.info();
                tauri::image::Image::new_owned(rgba, info.width, info.height)
            }

            let tray_icon = TrayIconBuilder::new()
                .icon(load_tray_icon())
                .menu(&menu)
                .on_menu_event(move |app, event| {
                    let id = event.id().as_ref();
                    if id == "show" {
                        if let Some(window) = app.get_webview_window("main") {
                            let state = app.state::<AppState>();
                            show_window(&window, &state);
                        }
                    } else if id == "quit" {
                        if let Some(mut child) = app.state::<AppState>().server_proc.lock().unwrap().take() {
                            let _ = child.kill();
                            let _ = child.wait();
                        }
                        app.exit(0);
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let state = app.state::<AppState>();
                            if *state.is_visible.lock().unwrap() {
                                hide_to_tray(&window, &state);
                            } else {
                                show_window(&window, &state);
                            }
                        }
                    }
                })
                .build(app)
                .unwrap();

            // Keep tray alive for app lifetime
            app.manage(TrayGuard(tray_icon));

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

struct TrayGuard(tauri::tray::TrayIcon);
unsafe impl Send for TrayGuard {}
unsafe impl Sync for TrayGuard {}
