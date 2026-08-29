from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from iceberg.data.models import (
    AdjustmentMode,
    CorporateActionStatus,
    IST,
    MarketDataMetadata,
)


def checksum_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metadata_for_file(
    path: str | Path,
    *,
    source: str,
    source_identifier: str,
    symbol: str,
    exchange: str,
    interval: str,
    adjustment_mode: AdjustmentMode,
    adjustment_methodology: str,
    corporate_action_status: CorporateActionStatus,
) -> MarketDataMetadata:
    path = Path(path)
    return MarketDataMetadata(
        source=source,
        source_identifier=source_identifier,
        ingestion_time=datetime.now(tz=IST),
        original_filename=path.name,
        checksum_sha256=checksum_file(path) if path.exists() else None,
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        start_date=None,
        end_date=None,
        adjustment_mode=adjustment_mode,
        adjustment_methodology=adjustment_methodology,
        corporate_action_status=corporate_action_status,
    )


def write_metadata(path: str | Path, metadata: MarketDataMetadata) -> None:
    Path(path).write_text(json.dumps(metadata.to_dict(), indent=2, sort_keys=True))
