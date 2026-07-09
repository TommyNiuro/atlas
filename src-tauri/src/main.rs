// Evita una consola extra en Windows release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::process::Command;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};

/// Puerto de la web de Atlas (servida por launchd io.niuro.atlas.web).
const PORT: u16 = 3005;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle().clone();
            // No bloqueamos la UI: mostramos el splash y navegamos cuando la web responde.
            std::thread::spawn(move || boot(&handle));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error al construir Atlas");
}

fn boot(app: &AppHandle) {
    ensure_services();
    let window = app.get_webview_window("main");
    if wait_for_port(PORT, Duration::from_secs(90)) {
        if let (Some(win), Ok(url)) = (
            &window,
            format!("http://localhost:{PORT}").parse::<tauri::Url>(),
        ) {
            let _ = win.navigate(url);
        }
    } else {
        show_error(
            app,
            "Los servicios de Atlas no respondieron. Revisa ~/atlas/logs/api.log y que colima este arriba.",
        );
    }
}

/// Asegura que los servicios (colima + postgres/redis + api + web) esten arriba.
/// Son launchd con KeepAlive; kickstart los levanta si estan detenidos, y el
/// wrapper atlas-api.sh de la api arranca colima + docker compose por su cuenta.
/// A diferencia del CRM, Atlas NO empaqueta el server: los servicios son daemons
/// que siguen corriendo (y sincronizando) aunque se cierre la ventana.
fn ensure_services() {
    let _ = Command::new("bash")
        .arg("-c")
        .arg("launchctl kickstart gui/$(id -u)/io.niuro.atlas.api gui/$(id -u)/io.niuro.atlas.web 2>/dev/null || true")
        .status();
}

fn wait_for_port(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    false
}

fn show_error(app: &AppHandle, msg: &str) {
    if let Some(win) = app.get_webview_window("main") {
        let safe = msg.replace('\\', "\\\\").replace('\'', "\\'");
        let js = format!(
            "var e=document.getElementById('msg'); if(e){{e.textContent='{safe}';}} var s=document.getElementById('spinner'); if(s){{s.style.display='none';}}"
        );
        let _ = win.eval(&js);
    }
}
