// VECTOR Desktop Shell — Tauri 2.x
//
// Wraps the Vite + React + Three.js dashboard at core/ui/dashboard/ in a
// native desktop window with system tray, IPC commands, and a backend
// health probe that targets the FastAPI server on https://127.0.0.1:8000.
//
// Build:
//   cd desktop/src-tauri
//   cargo tauri dev      # hot-reload dev with frontend at :5173
//   cargo tauri build    # produces installable bundle (msi/nsis/dmg/deb)

use serde::Serialize;
use std::sync::Mutex;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, State,
};

// ── Backend health state ─────────────────────────────────────────────────────

#[derive(Default)]
struct BackendState {
    last_status: Mutex<String>,
}

#[derive(Serialize, Clone)]
struct BackendHealth {
    reachable: bool,
    status_code: u16,
    latency_ms: u128,
    detail: String,
}

#[tauri::command]
async fn check_backend(state: State<'_, BackendState>) -> Result<BackendHealth, String> {
    let start = std::time::Instant::now();
    let client = reqwest::Client::builder()
        .danger_accept_invalid_certs(true) // VECTOR uses self-signed localhost cert
        .timeout(std::time::Duration::from_secs(3))
        .build()
        .map_err(|e| e.to_string())?;
    let url = "https://127.0.0.1:8000/health";
    let result = match client.get(url).send().await {
        Ok(resp) => BackendHealth {
            reachable: resp.status().is_success(),
            status_code: resp.status().as_u16(),
            latency_ms: start.elapsed().as_millis(),
            detail: format!("VECTOR backend reachable @ {url}"),
        },
        Err(e) => BackendHealth {
            reachable: false,
            status_code: 0,
            latency_ms: start.elapsed().as_millis(),
            detail: format!("VECTOR backend unreachable: {e}"),
        },
    };
    if let Ok(mut s) = state.last_status.lock() {
        *s = if result.reachable { "online".into() } else { "offline".into() };
    }
    Ok(result)
}

#[tauri::command]
fn get_backend_state(state: State<'_, BackendState>) -> String {
    state.last_status.lock().map(|s| s.clone()).unwrap_or_else(|_| "unknown".into())
}

#[tauri::command]
fn open_log_folder(_app: AppHandle) -> Result<(), String> {
    // Open the user's VECTOR log folder; the path is set by run_vector.py.
    let home = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .unwrap_or_else(|_| ".".into());
    let log_path = format!("{home}/.vector/logs");
    open::that(&log_path).map_err(|e| e.to_string())
}

#[tauri::command]
fn quit_app(app: AppHandle) {
    app.exit(0);
}

// ── App entry ────────────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_process::init())
        .manage(BackendState::default())
        .invoke_handler(tauri::generate_handler![
            check_backend,
            get_backend_state,
            open_log_folder,
            quit_app,
        ])
        .setup(|app| {
            // Build a small system-tray menu.
            let show_item = MenuItem::with_id(app, "show", "Show VECTOR", true, None::<&str>)?;
            let hide_item = MenuItem::with_id(app, "hide", "Hide window", true, None::<&str>)?;
            let logs_item = MenuItem::with_id(app, "logs", "Open log folder", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit VECTOR", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &hide_item, &logs_item, &quit_item])?;

            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .show_menu_on_left_click(true)
                .tooltip("VECTOR — running")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "hide" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.hide();
                        }
                    }
                    "logs" => {
                        let _ = open_log_folder(app.clone());
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::DoubleClick { .. } = event {
                        if let Some(w) = tray.app_handle().get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                })
                .build(app)?;

            // Periodic backend health probe — emit "backend://health" every 30s.
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                loop {
                    let state: State<BackendState> = app_handle.state();
                    if let Ok(result) = check_backend(state).await {
                        let _ = app_handle.emit("backend://health", &result);
                    }
                    tokio::time::sleep(std::time::Duration::from_secs(30)).await;
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running VECTOR desktop");
}

fn main() {
    run();
}
