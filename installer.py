from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from tkinter import Tk, messagebox


APP_NAME = "Ergene AI Photo Culling"
EXE_NAME = "ErgeneAI_PhotoCulling.exe"
LEGACY_EXE_NAMES = [EXE_NAME, "ErgeneAI_PhotoCulling_App.exe"]


def get_resource_path(relative_path: str) -> Path:
    """PyInstaller içindeki gömülü dosyaların gerçek yolunu bulur."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent / relative_path


def get_install_dir() -> Path:
    """Kullanıcı yetkisi gerektirmeyen güvenli kurulum klasörünü döndürür."""
    local_app_data = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    return local_app_data / "Programs" / APP_NAME


def stop_running_application() -> None:
    """Güncelleme sırasında kilitlenmeyi önlemek için açık uygulamayı kapatır."""
    for exe_name in LEGACY_EXE_NAMES:
        subprocess.run(
            ["taskkill", "/F", "/IM", exe_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )


def create_shortcut(shortcut_path: Path, target_path: Path, working_dir: Path, icon_path: Path) -> None:
    """Windows kısayolunu PowerShell üzerinden oluşturur."""
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = '{target_path}'
$Shortcut.WorkingDirectory = '{working_dir}'
$Shortcut.IconLocation = '{icon_path}'
$Shortcut.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def install_application() -> Path:
    """Ana uygulamayı kurar ve kısayolları hazırlar."""
    source_exe = get_resource_path(f"payload/{EXE_NAME}")
    if not source_exe.exists():
        raise FileNotFoundError("Kurulum paketi içinde ana uygulama dosyası bulunamadı.")

    stop_running_application()

    install_dir = get_install_dir()
    install_dir.mkdir(parents=True, exist_ok=True)

    target_exe = install_dir / EXE_NAME
    shutil.copy2(source_exe, target_exe)

    desktop_dir = Path(os.getenv("USERPROFILE", str(Path.home()))) / "Desktop"
    start_menu_dir = Path(os.getenv("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

    create_shortcut(
        desktop_dir / f"{APP_NAME}.lnk",
        target_exe,
        install_dir,
        target_exe,
    )
    create_shortcut(
        start_menu_dir / f"{APP_NAME}.lnk",
        target_exe,
        install_dir,
        target_exe,
    )

    return target_exe


def launch_application(target_exe: Path) -> None:
    """Kurulumdan sonra uygulamayı başlatır."""
    subprocess.Popen(
        [str(target_exe)],
        cwd=str(target_exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def main() -> int:
    if "--silent" in sys.argv:
        try:
            target_exe = install_application()
            if "--no-launch" not in sys.argv:
                launch_application(target_exe)
            return 0
        except Exception as exc:
            print(f"Kurulum tamamlanamadı: {exc}")
            return 1

    root = Tk()
    root.withdraw()

    try:
        target_exe = install_application()
    except Exception as exc:
        messagebox.showerror(
            "Kurulum Tamamlanamadı",
            f"Ergene AI Photo Culling kurulamadı.\n\nHata: {exc}",
        )
        return 1

    should_launch = messagebox.askyesno(
        "Kurulum Tamamlandı",
        "Ergene AI Photo Culling başarıyla kuruldu.\n\nUygulamayı şimdi başlatmak ister misiniz?",
    )

    if should_launch:
        launch_application(target_exe)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
