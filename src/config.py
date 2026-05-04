from __future__ import annotations

CATEGORY_SELECTED = "selected"
CATEGORY_REVIEW = "review"
CATEGORY_REJECTED = "rejected"
CATEGORY_DUPLICATES = "duplicates"

STANDARD_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
WEB_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
RAW_IMAGE_EXTENSIONS = {
    ".raw",
    ".cr2",
    ".cr3",
    ".nef",
    ".arw",
    ".dng",
    ".orf",
    ".rw2",
    ".raf",
    ".pef",
    ".srw",
}
SUPPORTED_EXTENSIONS = STANDARD_IMAGE_EXTENSIONS | RAW_IMAGE_EXTENSIONS

SELECTED_THRESHOLD = 80.0
REVIEW_THRESHOLD = 55.0

BLUR_WEIGHT = 0.45
BRIGHTNESS_WEIGHT = 0.20
CONTRAST_WEIGHT = 0.20
FACE_WEIGHT = 0.15

SIMILARITY_HASH_THRESHOLD = 5

BLUR_VARIANCE_REFERENCE = 500.0
CONTRAST_REFERENCE = 80.0
BRIGHTNESS_TARGET = 127.5
