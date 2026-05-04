from __future__ import annotations

import argparse
from pathlib import Path

from src.pipeline import CullingResult, process_culling


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Yerel çalışan fotoğraf ayıklama sistemi."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Analiz edilecek fotoğrafların bulunduğu klasör.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Sonuçların yazılacağı çıktı klasörü.",
    )
    return parser.parse_args()


def print_summary(
    result: CullingResult,
) -> None:
    print("\nİşlem özeti")
    print("------------")
    print(f"Toplam işlenen fotoğraf: {result.summary.total}")
    print(f"Selected sayısı: {result.summary.selected}")
    print(f"Review sayısı: {result.summary.review}")
    print(f"Rejected sayısı: {result.summary.rejected}")
    print(f"Benzer/aynı görsel sayısı: {result.summary.duplicates}")
    print(f"Hatalı/atlanmış dosya sayısı: {result.summary.skipped}")
    print(f"CSV rapor konumu: {result.csv_path}")
    print(f"JSON rapor konumu: {result.json_path}")


def main() -> int:
    args = parse_args()
    input_dir: Path = args.input
    output_dir: Path = args.output

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Hata: Giriş klasörü bulunamadı: {input_dir}")
        return 1

    result = process_culling(input_dir, output_dir, logger=print)

    if result.summary.total == 0:
        print_summary(result)
        print("Desteklenen ve işlenebilir fotoğraf bulunamadı.")
        return 0

    print_summary(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
