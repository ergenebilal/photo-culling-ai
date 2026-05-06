from __future__ import annotations

from typing import Any

import imagehash
from PIL import Image

from src.config import SIMILARITY_HASH_THRESHOLD


def mark_similar_groups(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hashes: list[tuple[int, imagehash.ImageHash]] = []

    for index, record in enumerate(records):
        try:
            image = record["image_for_hash"]
            if not isinstance(image, Image.Image):
                raise TypeError("Hash için geçerli Pillow görüntüsü yok.")
            hashes.append((index, imagehash.phash(image)))
        except Exception:
            record["similarity_group_id"] = f"group_{index + 1}"
            record["similarity_group_size"] = 1
            record["best_in_group"] = True
            record["is_duplicate"] = False
            record["duplicate_of"] = ""

    groups = _build_groups(hashes)

    for group_number, group_indexes in enumerate(groups, start=1):
        group_id = f"group_{group_number}"
        group_size = len(group_indexes)
        best_index = max(group_indexes, key=lambda item: records[item]["final_score"])
        best_filename = records[best_index]["filename"]

        for record_index in group_indexes:
            records[record_index]["similarity_group_id"] = group_id
            records[record_index]["similarity_group_size"] = group_size
            records[record_index]["best_in_group"] = record_index == best_index
            records[record_index]["is_duplicate"] = record_index != best_index
            records[record_index]["duplicate_of"] = "" if record_index == best_index else best_filename

    for record in records:
        record.setdefault("similarity_group_size", 1)
        record.setdefault("is_duplicate", False)
        record.setdefault("duplicate_of", "")
        record.pop("image_for_hash", None)

    return records


def _build_groups(hashes: list[tuple[int, imagehash.ImageHash]]) -> list[list[int]]:
    groups: list[list[int]] = []
    visited: set[int] = set()
    hash_map = dict(hashes)

    for index, current_hash in hashes:
        if index in visited:
            continue

        group = [index]
        visited.add(index)

        for other_index, other_hash in hashes:
            if other_index in visited:
                continue

            if current_hash - other_hash <= SIMILARITY_HASH_THRESHOLD:
                group.append(other_index)
                visited.add(other_index)

        # Grup içinde dolaylı benzerlikleri de yakalamak için kısa bir genişletme yapılır.
        changed = True
        while changed:
            changed = False
            for candidate_index, candidate_hash in hashes:
                if candidate_index in visited:
                    continue
                if any(
                    candidate_hash - hash_map[group_index] <= SIMILARITY_HASH_THRESHOLD
                    for group_index in group
                ):
                    group.append(candidate_index)
                    visited.add(candidate_index)
                    changed = True

        groups.append(group)

    return groups
