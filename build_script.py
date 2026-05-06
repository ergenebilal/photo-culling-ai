import PyInstaller.__main__
from pathlib import Path

import cv2
from PIL import Image


def ensure_icon_file(base_path: Path) -> Path | None:
    # PNG logo varsa Windows EXE için çok boyutlu ICO dosyası üretir.
    png_path = base_path / "static" / "ergene-ai-logo.png"
    icon_path = base_path / "static" / "ergene-ai-logo.ico"

    if icon_path.exists():
        return icon_path

    if not png_path.exists():
        return None

    with Image.open(png_path) as image:
        image = image.convert("RGBA")
        image.save(
            icon_path,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )

    return icon_path

def build():
    # Mevcut dizin
    base_path = Path(__file__).resolve().parent
    
    # Web arayüzlü uygulamayı tek EXE olarak paketler.
    params = [
        'start_app.py',
        '--name=ErgeneAI_PhotoCulling',
        '--onefile',
        '--windowed',
        '--add-data=templates;templates',
        '--add-data=static;static',
        '--hidden-import=uvicorn.logging',
        '--hidden-import=uvicorn.loops',
        '--hidden-import=uvicorn.loops.auto',
        '--hidden-import=uvicorn.protocols',
        '--hidden-import=uvicorn.protocols.http',
        '--hidden-import=uvicorn.protocols.http.auto',
        '--hidden-import=uvicorn.protocols.websockets',
        '--hidden-import=uvicorn.protocols.websockets.auto',
        '--hidden-import=uvicorn.lifespan',
        '--hidden-import=uvicorn.lifespan.on',
        '--clean',
    ]

    # Logo ikonunu EXE dosyasına ekle
    icon_path = ensure_icon_file(base_path)
    if icon_path:
        params.append(f'--icon={icon_path}')

    # OpenCV yüz tespit modeli EXE içindeki multiprocessing worker'larda da bulunmalıdır.
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if cascade_path.exists():
        params.append(f'--add-data={cascade_path};cv2/data')

    print("Paketleme işlemi başlatılıyor... Bu işlem birkaç dakika sürebilir.")
    PyInstaller.__main__.run(params)
    print("\nİşlem Tamamlandı! EXE dosyanız 'dist' klasörü içindedir.")

if __name__ == "__main__":
    build()
