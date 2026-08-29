import pytest

from iceberg.exceptions import FailClosedError
from iceberg.features.pipeline import FeaturePipeline, FeatureValue

from tests.conftest import D, ist_datetime


def test_future_feature_timestamp_fails_closed():
    features = [FeatureValue("future_alpha", D("1"), ist_datetime(10, 1))]

    with pytest.raises(FailClosedError):
        FeaturePipeline().validate_no_future_features(features, ist_datetime(10, 0))
