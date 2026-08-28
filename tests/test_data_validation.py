from datetime import timedelta

import pytest

from iceberg.data.validation import DataValidationError, DataValidator
from iceberg.domain.models import Candle

from tests.conftest import D, ist_datetime


def candle(symbol="ABC", timestamp=None, open_="10", high="11", low="9", close="10", volume="1000"):
    return Candle(
        symbol=symbol,
        timestamp=timestamp or ist_datetime(10, 0),
        open=D(open_),
        high=D(high),
        low=D(low),
        close=D(close),
        volume=D(volume),
    )


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"open_": "0"}, "NON_POSITIVE_PRICE"),
        ({"high": "8", "low": "9"}, "HIGH_LESS_THAN_LOW"),
        ({"open_": "12"}, "OPEN_OUTSIDE_RANGE"),
        ({"close": "12"}, "CLOSE_OUTSIDE_RANGE"),
        ({"volume": "-1"}, "INVALID_VOLUME"),
        ({"symbol": "XYZ"}, "SYMBOL_MISMATCH"),
    ],
)
def test_data_validator_rejects_bad_candles(kwargs, reason):
    with pytest.raises(DataValidationError) as exc:
        DataValidator(max_staleness=timedelta(minutes=5)).validate_candles(
            [candle(**kwargs)],
            expected_symbol="ABC",
            now=ist_datetime(10, 1),
        )

    assert exc.value.reason == reason


def test_data_validator_rejects_duplicates_and_non_monotonic_timestamps():
    validator = DataValidator(max_staleness=timedelta(minutes=5))

    with pytest.raises(DataValidationError) as exc:
        validator.validate_candles(
            [candle(timestamp=ist_datetime(10, 0)), candle(timestamp=ist_datetime(10, 0))],
            expected_symbol="ABC",
            now=ist_datetime(10, 1),
        )
    assert exc.value.reason == "DUPLICATE_CANDLE"

    with pytest.raises(DataValidationError) as exc:
        validator.validate_candles(
            [candle(timestamp=ist_datetime(10, 1)), candle(timestamp=ist_datetime(10, 0))],
            expected_symbol="ABC",
            now=ist_datetime(10, 2),
        )
    assert exc.value.reason == "NON_MONOTONIC_TIMESTAMPS"
