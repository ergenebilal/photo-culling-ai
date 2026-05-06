from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from src.pipeline import process_culling


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Yerel çalışan AI fotoğraf ayıklama sistemi."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Analiz edilecek fotoğrafların bulunduğu klasör.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Seçilen ve elenen fotoğrafların yazılacağı çıktı klasörü.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Hata: giriş klasörü bulunamadı: {input_dir}")
        return 1

    print("Fotoğraf ayıklama işlemi başlatıldı.")
    print(f"Giriş klasörü: {input_dir}")
    print(f"Çıkış klasörü: {output_dir}")

    result = process_culling(
        input_dir=input_dir,
        output_dir=output_dir,
        logger=print,
        max_workers=1,
    )

    print("\nİşlem tamamlandı.")
    print(f"Toplam işlenen fotoğraf: {result.summary.total}")
    print(f"Seçilen fotoğraf sayısı: {result.summary.selected}")
    print(f"Elenen fotoğraf sayısı: {result.summary.rejected}")
    print(f"Hatalı/atlanmış dosya sayısı: {result.summary.skipped}")
    print(f"CSV raporu: {result.csv_path}")
    print(f"JSON raporu: {result.json_path}")

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
