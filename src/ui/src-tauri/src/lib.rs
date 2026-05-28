use tauri::{Emitter, Manager, WebviewWindow};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use std::sync::Mutex;

const FLOAT_SIZE: (u32, u32) = (60, 60);
const CHAT_SIZE: (u32, u32) = (400, 600);
const CHAT_MAX: (u32, u32) = (900, 1000);
const MARGIN: i32 = 20;

struct AppState {
    is_chat: Mutex<bool>,
    float_pos: Mutex<Option<(i32, i32)>>,
    chat_pos: Mutex<Option<(i32, i32)>>,
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

#[tauri::command]
async fn toggle_mode(window: WebviewWindow, state: tauri::State<'_, AppState>) -> Result<String, String> {
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
    let mut is_chat = state.is_chat.lock().map_err(|e| e.to_string())?;
    if !*is_chat {
        switch_to_chat(&window, &state);
        *is_chat = true;
    }
    Ok("chat".into())
}

#[tauri::command]
async fn set_floating(window: WebviewWindow, state: tauri::State<'_, AppState>) -> Result<String, String> {
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
            float_pos: Mutex::new(None),
            chat_pos: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            toggle_mode, set_chat, set_floating,
            start_native_drag, get_mode, open_url_in_browser
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();
            let (x, y) = default_float_pos(&window);
            let _ = window.set_position(tauri::LogicalPosition::new(x as f64, y as f64));
            let _ = window.set_resizable(false);
            let _ = app.global_shortcut().register(
                Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyT),
            );
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
