from __future__ import annotations

import csv
import json
from pathlib import Path

from iceberg.data.models import HistoricalBar, MarketDataMetadata, NormalizedDataset


class LocalMarketDataRepository:
    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)
        self.raw_dir = self.root / "raw"
        self.normalized_dir = self.root / "normalized"
        self.derived_dir = self.root / "derived"

    def ensure_directories(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_dir.mkdir(parents=True, exist_ok=True)
        self.derived_dir.mkdir(parents=True, exist_ok=True)

    def write_normalized_dataset(self, dataset: NormalizedDataset, name: str) -> tuple[Path, Path, Path]:
        self.ensure_directories()
        csv_path = self.normalized_dir / f"{name}.csv"
        metadata_path = self.normalized_dir / f"{name}.metadata.json"
        quality_path = self.normalized_dir / f"{name}.quality.json"
        write_bars_csv(csv_path, dataset.bars)
        metadata_path.write_text(json.dumps(dataset.metadata.to_dict(), indent=2, sort_keys=True))
        quality_path.write_text(json.dumps(dataset.quality_report.to_dict(), indent=2, sort_keys=True))
        return csv_path, metadata_path, quality_path


def write_bars_csv(path: str | Path, bars: tuple[HistoricalBar, ...] | list[HistoricalBar]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        fieldnames = [
            "timestamp",
            "symbol",
            "exchange",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "interval",
            "source_id",
            "ingested_at",
            "trading_date",
            "timezone",
            "adjustment_mode",
            "corporate_action_status",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for bar in bars:
            writer.writerow(bar.to_dict())
