from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from app.config import get_settings
from app.database import DatabaseManager
from sqlalchemy import text

EXPECTED_DOCUMENTS = 182
EXPECTED_CHUNKS = 821
EXPECTED_PARSED_ATTACHMENTS = 60
EXPECTED_ATTACHMENT_FILES = 69
EXPECTED_COLLECTION = "odirag_chunks_bailian_v4"
ROLLBACK_COLLECTION = "odirag_chunks"
EXPECTED_DIMENSIONS = 1536
EXPECTED_DISTANCE = "cosine"


class VerificationError(RuntimeError):
    pass


def _vector_shape(result: dict[str, Any]) -> tuple[int, str]:
    vectors = result.get("config", {}).get("params", {}).get("vectors")
    if not isinstance(vectors, dict) or "size" not in vectors or "distance" not in vectors:
        raise VerificationError("unexpected_vector_configuration")
    return int(vectors["size"]), str(vectors["distance"]).lower()


def _validate_id_sets(postgres_ids: list[str], payload_ids: list[str], point_ids: list[str]) -> str:
    if len(postgres_ids) != EXPECTED_CHUNKS or len(payload_ids) != EXPECTED_CHUNKS:
        raise VerificationError("chunk_id_count_mismatch")
    if len(postgres_ids) != len(set(postgres_ids)):
        raise VerificationError("duplicate_postgres_chunk_id")
    if len(payload_ids) != len(set(payload_ids)):
        raise VerificationError("duplicate_qdrant_payload_chunk_id")
    if payload_ids != point_ids:
        raise VerificationError("qdrant_point_payload_id_mismatch")
    if set(postgres_ids) != set(payload_ids):
        raise VerificationError("postgres_qdrant_chunk_id_set_mismatch")
    return hashlib.sha256(
        ("\n".join(sorted(postgres_ids)) + "\n").encode("utf-8")
    ).hexdigest()


async def _postgres_state() -> tuple[tuple[int, int, int, int, int], list[str]]:
    settings = get_settings()
    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            counts = (
                await session.execute(
                    text(
                        """
                        SELECT
                          (SELECT count(*) FROM documents),
                          (SELECT count(*) FROM chunks),
                          (SELECT count(*) FROM attachments WHERE parse_status = 'parsed'),
                          (SELECT count(*) FROM (
                            SELECT chunk_id FROM chunks GROUP BY chunk_id HAVING count(*) > 1
                          ) duplicate_chunk_ids),
                          (SELECT count(*) FROM (
                            SELECT document_id, chunk_index
                            FROM chunks
                            GROUP BY document_id, chunk_index
                            HAVING count(*) > 1
                          ) duplicate_document_chunk_pairs)
                        """
                    )
                )
            ).one()
            result = await session.execute(text("SELECT chunk_id FROM chunks ORDER BY chunk_id"))
            chunk_ids = [str(value) for value in result.scalars().all()]
            await session.rollback()
            return tuple(int(value) for value in counts), chunk_ids  # type: ignore[return-value]
    finally:
        await database.dispose()


async def _qdrant_state() -> tuple[dict[str, Any], dict[str, Any], list[str], list[str]]:
    settings = get_settings()
    api_key = settings.qdrant_api_key
    headers = {"api-key": api_key.get_secret_value()} if api_key else {}
    collection = quote(EXPECTED_COLLECTION, safe="")
    base_url = settings.qdrant_url.rstrip("/")
    payload_ids: list[str] = []
    point_ids: list[str] = []
    offset: str | int | None = None
    observed_offsets: set[str] = set()

    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        response = await client.get(f"{base_url}/collections/{collection}")
        response.raise_for_status()
        result = response.json().get("result")
        if not isinstance(result, dict):
            raise VerificationError("invalid_qdrant_collection_response")

        while True:
            body: dict[str, Any] = {
                "limit": 256,
                "with_payload": ["chunk_id"],
                "with_vector": False,
            }
            if offset is not None:
                body["offset"] = offset
            response = await client.post(
                f"{base_url}/collections/{collection}/points/scroll", json=body
            )
            response.raise_for_status()
            page = response.json().get("result")
            if not isinstance(page, dict) or not isinstance(page.get("points"), list):
                raise VerificationError("invalid_qdrant_scroll_response")
            for point in page["points"]:
                if not isinstance(point, dict) or not isinstance(point.get("payload"), dict):
                    raise VerificationError("invalid_qdrant_point")
                chunk_id = point["payload"].get("chunk_id")
                if not isinstance(chunk_id, str) or not chunk_id:
                    raise VerificationError("missing_qdrant_payload_chunk_id")
                payload_ids.append(chunk_id)
                point_ids.append(str(point.get("id")))
            offset = page.get("next_page_offset")
            if offset is None:
                break
            offset_key = str(offset)
            if offset_key in observed_offsets:
                raise VerificationError("qdrant_scroll_offset_cycle")
            observed_offsets.add(offset_key)

        rollback = await client.get(
            f"{base_url}/collections/{quote(ROLLBACK_COLLECTION, safe='')}"
        )
        if rollback.status_code != 200:
            raise VerificationError("rollback_qdrant_collection_missing")
        rollback_result = rollback.json().get("result")
        if not isinstance(rollback_result, dict):
            raise VerificationError("invalid_rollback_qdrant_response")
        return result, rollback_result, payload_ids, point_ids


async def main() -> None:
    settings = get_settings()
    if settings.vector_store_provider != "qdrant":
        raise VerificationError("unexpected_vector_store_provider")
    if settings.qdrant_collection != EXPECTED_COLLECTION:
        raise VerificationError("unexpected_active_qdrant_collection")

    counts, postgres_ids = await _postgres_state()
    documents, chunks, parsed_attachments, duplicate_chunks, duplicate_pairs = counts
    if (documents, chunks, parsed_attachments) != (
        EXPECTED_DOCUMENTS,
        EXPECTED_CHUNKS,
        EXPECTED_PARSED_ATTACHMENTS,
    ):
        raise VerificationError("postgres_production_counts_changed")
    if duplicate_chunks or duplicate_pairs:
        raise VerificationError("postgres_duplicate_invariant_failed")

    attachment_root = Path(settings.data_dir) / "attachments"
    attachment_files = sum(1 for path in attachment_root.rglob("*") if path.is_file())
    if attachment_files != EXPECTED_ATTACHMENT_FILES:
        raise VerificationError("attachment_file_count_changed")

    qdrant, rollback_qdrant, payload_ids, point_ids = await _qdrant_state()
    status = str(qdrant.get("status", "")).lower()
    points = int(qdrant.get("points_count") or 0)
    dimensions, distance = _vector_shape(qdrant)
    if status != "green" or points != EXPECTED_CHUNKS:
        raise VerificationError("active_qdrant_collection_unhealthy")
    if dimensions != EXPECTED_DIMENSIONS or distance != EXPECTED_DISTANCE:
        raise VerificationError("active_qdrant_collection_shape_mismatch")
    rollback_status = str(rollback_qdrant.get("status", "")).lower()
    rollback_points = int(rollback_qdrant.get("points_count") or 0)
    rollback_dimensions, rollback_distance = _vector_shape(rollback_qdrant)
    if rollback_status != "green" or rollback_points != EXPECTED_CHUNKS:
        raise VerificationError("rollback_qdrant_collection_unhealthy")
    if (
        rollback_dimensions != EXPECTED_DIMENSIONS
        or rollback_distance != EXPECTED_DISTANCE
    ):
        raise VerificationError("rollback_qdrant_collection_shape_mismatch")
    chunk_ids_digest = _validate_id_sets(postgres_ids, payload_ids, point_ids)

    print(
        "production_data_integrity=PASS-LIVE "
        f"documents={documents} chunks={chunks} parsed_attachments={parsed_attachments} "
        f"attachment_files={attachment_files} duplicate_chunk_id={duplicate_chunks} "
        f"duplicate_document_chunk_index={duplicate_pairs} qdrant_status={status} "
        f"qdrant_points={points} qdrant_dimensions={dimensions} distance={distance} "
        f"rollback_qdrant_status={rollback_status} rollback_qdrant_points={rollback_points} "
        f"rollback_qdrant_dimensions={rollback_dimensions} rollback_distance={rollback_distance} "
        "duplicate_qdrant_payload_chunk_id=0 point_payload_ids_equal=true "
        f"postgres_qdrant_id_set_equal=true chunk_ids_sha256={chunk_ids_digest}"
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - expose only the safe exception type.
        print(f"production_data_integrity=FAIL error_type={type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
