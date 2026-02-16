"""Validation wrapper layer between parsers and persistence.

Validates dicts against Pydantic models, quarantines failures, and
provides batch-level integrity checks (player count, economy alignment).

Usage::

    from scraper.validation import validate_and_quarantine, validate_batch
    from scraper.models import PlayerStatsModel

    validated = validate_and_quarantine(data, PlayerStatsModel, ctx, repo)
    if validated is not None:
        repo.upsert_player_stats(validated)
"""

import json
import logging
import warnings
from datetime import datetime, timezone

from pydantic import ValidationError

logger = logging.getLogger(__name__)


def validate_and_quarantine(
    data: dict,
    model_cls: type,
    context: dict,
    repo=None,
) -> dict | None:
    """Validate a dict against a Pydantic model, quarantining failures.

    Args:
        data: Dict of field values to validate.
        model_cls: Pydantic model class (e.g. MatchModel).
        context: Dict with ``match_id`` and ``map_number`` for logging
            and quarantine record creation.
        repo: MatchRepository instance. If None, quarantine insertion
            is skipped (useful for dry-run or test scenarios).

    Returns:
        The validated dict (via ``model.model_dump()``) on success,
        or ``None`` if validation failed (record was quarantined).
    """
    # Ensure updated_at key exists -- Pydantic models default to ""
    # but UPSERT SQL references :updated_at, so the key must be present.
    if "updated_at" not in data:
        data["updated_at"] = data.get("scraped_at", "")

    match_id = context.get("match_id")
    map_number = context.get("map_number")

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = model_cls.model_validate(data)

        # Log any soft-validation warnings that were emitted
        for w in caught:
            logger.warning(
                "Validation warning for %s (match %s, map %s): %s",
                model_cls.__name__,
                match_id,
                map_number,
                w.message,
            )

        return model.model_dump()

    except ValidationError as e:
        logger.error(
            "Validation failed for %s (match %s, map %s): %s",
            model_cls.__name__,
            match_id,
            map_number,
            e,
        )

        quarantine_record = {
            "entity_type": model_cls.__name__,
            "match_id": match_id,
            "map_number": map_number,
            "raw_data": json.dumps(data, default=str),
            "error_details": str(e),
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
            "resolved": 0,
        }

        if repo is not None:
            try:
                repo.insert_quarantine(quarantine_record)
            except Exception:
                logger.exception(
                    "Failed to insert quarantine record for %s (match %s)",
                    model_cls.__name__,
                    match_id,
                )

        return None


def validate_batch(
    items: list[dict],
    model_cls: type,
    context: dict,
    repo=None,
) -> tuple[list[dict], int]:
    """Validate a list of dicts, returning valid results and quarantine count.

    Args:
        items: List of dicts to validate.
        model_cls: Pydantic model class.
        context: Dict with ``match_id`` and ``map_number``.
        repo: MatchRepository instance (or None).

    Returns:
        Tuple of (list of validated dicts, number of quarantined items).
    """
    valid: list[dict] = []
    quarantine_count = 0

    for item in items:
        result = validate_and_quarantine(item, model_cls, context, repo)
        if result is not None:
            valid.append(result)
        else:
            quarantine_count += 1

    return valid, quarantine_count


def check_player_count(
    stats_dicts: list[dict],
    match_id: int,
    map_number: int,
) -> list[str]:
    """Check that a map has exactly 10 player stats rows (2 teams of 5).

    This is a warn-and-insert check -- irregular counts may occur with
    coach stand-ins or mid-match substitutions, so the data is not
    rejected.

    Args:
        stats_dicts: List of validated player_stats dicts for one map.
        match_id: For warning message context.
        map_number: For warning message context.

    Returns:
        List of warning strings (empty if count is exactly 10).
    """
    count = len(stats_dicts)
    if count != 10:
        return [
            f"Expected 10 player stats for match {match_id} map "
            f"{map_number}, got {count}"
        ]
    return []


def check_economy_alignment(
    economy_dicts: list[dict],
    valid_round_numbers: set[int],
    match_id: int,
    map_number: int,
) -> list[str]:
    """Check that all economy round numbers exist in round_history.

    Defense-in-depth: the orchestrator already filters economy rows to
    valid round numbers, but this catches any slip-through.

    Args:
        economy_dicts: List of validated economy dicts.
        valid_round_numbers: Set of round numbers from round_history.
        match_id: For warning message context.
        map_number: For warning message context.

    Returns:
        List of warning strings for misaligned rounds (empty = clean).
    """
    warnings_list: list[str] = []
    for econ in economy_dicts:
        rn = econ.get("round_number")
        if rn is not None and rn not in valid_round_numbers:
            warnings_list.append(
                f"Economy round {rn} not in round_history for "
                f"match {match_id} map {map_number}"
            )
    return warnings_list
