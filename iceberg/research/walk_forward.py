from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class TimeRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("time range end must be on or after start")


@dataclass(frozen=True)
class TrainValidationTestSplit:
    train: TimeRange
    validation: TimeRange
    test: TimeRange
    shuffled: bool = False

    def __post_init__(self) -> None:
        if self.shuffled:
            raise ValueError("financial time series splits must not be shuffled")
        if not (self.train.end < self.validation.start and self.validation.end < self.test.start):
            raise ValueError("train, validation, and test ranges must be chronological")


class WalkForwardSplitter:
    def train_validation_test(self, train: TimeRange, validation: TimeRange, test: TimeRange) -> TrainValidationTestSplit:
        return TrainValidationTestSplit(train, validation, test)

    def rolling(
        self,
        *,
        start: date,
        end: date,
        train_days: int,
        validation_days: int,
        test_days: int,
        step_days: int,
    ) -> list[TrainValidationTestSplit]:
        splits = []
        cursor = start
        while True:
            train = TimeRange(cursor, cursor + timedelta(days=train_days - 1))
            validation = TimeRange(train.end + timedelta(days=1), train.end + timedelta(days=validation_days))
            test = TimeRange(validation.end + timedelta(days=1), validation.end + timedelta(days=test_days))
            if test.end > end:
                break
            splits.append(TrainValidationTestSplit(train, validation, test))
            cursor += timedelta(days=step_days)
        return splits

    def expanding(
        self,
        *,
        start: date,
        end: date,
        initial_train_days: int,
        validation_days: int,
        test_days: int,
        step_days: int,
    ) -> list[TrainValidationTestSplit]:
        splits = []
        train_end = start + timedelta(days=initial_train_days - 1)
        while True:
            train = TimeRange(start, train_end)
            validation = TimeRange(train.end + timedelta(days=1), train.end + timedelta(days=validation_days))
            test = TimeRange(validation.end + timedelta(days=1), validation.end + timedelta(days=test_days))
            if test.end > end:
                break
            splits.append(TrainValidationTestSplit(train, validation, test))
            train_end += timedelta(days=step_days)
        return splits
