from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from iceberg.domain.models import require_aware


@dataclass(frozen=True)
class FeatureValue:
    name: str
    value: Decimal | str | int
    available_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.available_at, "available_at")


class FeaturePipeline:
    """Timestamped feature container that refuses future features."""

    def filter_available(self, features: list[FeatureValue], decision_time: datetime) -> tuple[FeatureValue, ...]:
        require_aware(decision_time, "decision_time")
        return tuple(feature for feature in features if feature.available_at <= decision_time)
