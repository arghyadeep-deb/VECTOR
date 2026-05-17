// VECTOR Desktop Shell — Tauri backend
// Wraps the JARVIS-style React UI in a native desktop window.
// Connects to VECTOR's core server at 127.0.0.1:8000

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

#[tauri::command]
fn get_vector_status() -> String {
    // In production: query VECTOR core API
    r#"{"status":"online","uptime":"00:00:00","activeAgents":3}"#.to_string()
}

#[tauri::command]
fn open_vector_core() {
    // Launch VECTOR Python core if not running
    #[cfg(target_os = "windows")]
    std::process::Command::new("cmd")
        .args(["/C", "start", "", "python", "run_vector.py"])
        .spawn()
        .ok();
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let window = app.get_window("main").unwrap();
            // Frameless JARVIS window
            window.set_decorations(false).ok();
            window.set_transparent(true).ok();
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_vector_status,
            open_vector_core,
        ])
        .run(tauri::generate_context!())
        .expect("error while running VECTOR desktop app");
}
