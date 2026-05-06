from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__


def build_setup() -> None:
    # Ana uygulama EXE dosyasını gömen kullanıcı dostu kurulum dosyası üretir.
    base_path = Path(__file__).resolve().parent
    app_exe = base_path / "dist" / "ErgeneAI_PhotoCulling.exe"
    icon_path = base_path / "static" / "ergene-ai-logo.ico"

    if not app_exe.exists():
        raise FileNotFoundError("Önce python build_script.py ile ana uygulama EXE dosyasını üretin.")

    params = [
        "installer.py",
        "--name=ErgeneAI_PhotoCulling_Setup",
        "--onefile",
        "--windowed",
        f"--add-data={app_exe};payload",
        "--clean",
    ]

    if icon_path.exists():
        params.append(f"--icon={icon_path}")

    print("Setup dosyası oluşturuluyor... Bu işlem birkaç dakika sürebilir.")
    PyInstaller.__main__.run(params)
    print("\nİşlem tamamlandı. Setup dosyası dist klasörüne yazıldı.")


if __name__ == "__main__":
    build_setup()
