use tauri::{Emitter, Manager, WebviewWindow};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use std::sync::Mutex;

const FLOAT_SIZE: (u32, u32) = (60, 60);
const CHAT_SIZE: (u32, u32) = (400, 600);
const MARGIN: i32 = 20;

struct AppState {
    is_chat: Mutex<bool>,
}

fn float_pos(window: &WebviewWindow) -> (i32, i32) {
    if let Some(m) = window.current_monitor().ok().flatten() {
        let s = m.size();
        (s.width as i32 - FLOAT_SIZE.0 as i32 - MARGIN, s.height as i32 - FLOAT_SIZE.1 as i32 - MARGIN)
    } else {
        (0, 0)
    }
}

fn chat_pos(window: &WebviewWindow) -> (i32, i32) {
    if let Some(m) = window.current_monitor().ok().flatten() {
        let s = m.size();
        (s.width as i32 - CHAT_SIZE.0 as i32 - MARGIN, s.height as i32 - CHAT_SIZE.1 as i32 - MARGIN)
    } else {
        (0, 0)
    }
}

fn switch_to_chat(window: &WebviewWindow) {
    let (x, y) = chat_pos(window);
    let _ = window.set_position(tauri::LogicalPosition::new(x as f64, y as f64));
    let _ = window.set_size(tauri::LogicalSize::new(CHAT_SIZE.0 as f64, CHAT_SIZE.1 as f64));
    let _ = window.set_min_size(Some(tauri::LogicalSize::new(CHAT_SIZE.0 as f64, CHAT_SIZE.1 as f64)));
    let _ = window.set_max_size(Some(tauri::LogicalSize::new(CHAT_SIZE.0 as f64, CHAT_SIZE.1 as f64)));
    let _ = window.set_resizable(false);
    let _ = window.set_focus();
    let _ = window.emit("mode-changed", "chat");
}

fn switch_to_float(window: &WebviewWindow) {
    let (x, y) = float_pos(window);
    let _ = window.set_position(tauri::LogicalPosition::new(x as f64, y as f64));
    let _ = window.set_size(tauri::LogicalSize::new(FLOAT_SIZE.0 as f64, FLOAT_SIZE.1 as f64));
    let _ = window.set_min_size(Some(tauri::LogicalSize::new(FLOAT_SIZE.0 as f64, FLOAT_SIZE.1 as f64)));
    let _ = window.set_max_size(Some(tauri::LogicalSize::new(FLOAT_SIZE.0 as f64, FLOAT_SIZE.1 as f64)));
    let _ = window.set_resizable(false);
    let _ = window.emit("mode-changed", "floating");
}

#[tauri::command]
async fn toggle_mode(window: WebviewWindow, state: tauri::State<'_, AppState>) -> Result<String, String> {
    let mut is_chat = state.is_chat.lock().map_err(|e| e.to_string())?;
    if *is_chat {
        switch_to_float(&window);
        *is_chat = false;
        Ok("floating".into())
    } else {
        switch_to_chat(&window);
        *is_chat = true;
        Ok("chat".into())
    }
}

#[tauri::command]
async fn set_chat(window: WebviewWindow, state: tauri::State<'_, AppState>) -> Result<String, String> {
    let mut is_chat = state.is_chat.lock().map_err(|e| e.to_string())?;
    if !*is_chat {
        switch_to_chat(&window);
        *is_chat = true;
    }
    Ok("chat".into())
}

#[tauri::command]
async fn set_floating(window: WebviewWindow, state: tauri::State<'_, AppState>) -> Result<String, String> {
    let mut is_chat = state.is_chat.lock().map_err(|e| e.to_string())?;
    if *is_chat {
        switch_to_float(&window);
        *is_chat = false;
    }
    Ok("floating".into())
}

#[tauri::command]
async fn start_native_drag(window: WebviewWindow) -> Result<(), String> {
    window.start_dragging().map_err(|e| e.to_string())
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
                                switch_to_float(&window);
                                *is_chat = false;
                            } else {
                                switch_to_chat(&window);
                                *is_chat = true;
                            }
                        }
                    }
                })
                .build(),
        )
        .manage(AppState {
            is_chat: Mutex::new(false),
        })
        .invoke_handler(tauri::generate_handler![
            toggle_mode, set_chat, set_floating,
            start_native_drag, get_mode
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();
            let (x, y) = float_pos(&window);
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
