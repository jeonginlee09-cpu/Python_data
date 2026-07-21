"""실습 4 데이터 정제 함수 테스트."""

import pandas as pd
from pandas.testing import assert_frame_equal

from solution import (
    clean_price,
    fill_missing,
    normalize_types,
    remove_outliers,
    winsorize,
)


def sample_raw() -> pd.DataFrame:
    """결측, 음수 가격, 타입 불일치를 포함한 작은 테스트 데이터."""
    return pd.DataFrame(
        {
            "order_id": ["A", "B", "C", "D", "E"],
            "order_date": [
                "2025-01-01",
                "2025-01-02",
                None,
                "2025-01-04",
                "2025-01-05",
            ],
            "region": ["Seoul", None, "Busan", "Seoul", "Busan"],
            "category": ["Food", "Food", "Food", "Food", "Food"],
            "quantity": ["1", "2", "3", "4", "1000"],
            "unit_price": ["100", None, "-50", "130", "10000"],
            "discount": ["0", "0.1", None, "0", "0.05"],
        }
    )


def test_normalize_types_converts_columns_without_changing_original() -> None:
    raw = sample_raw()
    original = raw.copy(deep=True)

    result = normalize_types(raw)

    assert_frame_equal(raw, original)
    assert pd.api.types.is_numeric_dtype(result["quantity"])
    assert pd.api.types.is_numeric_dtype(result["unit_price"])
    assert pd.api.types.is_datetime64_any_dtype(result["order_date"])
    assert isinstance(result["category"].dtype, pd.CategoricalDtype)
    assert isinstance(result["region"].dtype, pd.CategoricalDtype)


def test_clean_price_replaces_invalid_prices_with_category_median() -> None:
    typed = normalize_types(sample_raw())
    original = typed.copy(deep=True)

    result = clean_price(typed)

    assert_frame_equal(typed, original)
    assert result["unit_price"].isna().sum() == 0
    assert (result["unit_price"] > 0).all()
    assert result.loc[1, "unit_price"] == 130
    assert result.loc[2, "unit_price"] == 130


def test_fill_missing_removes_non_price_missing_values() -> None:
    typed = normalize_types(sample_raw())
    priced = clean_price(typed)

    result = fill_missing(priced)

    assert result["region"].isna().sum() == 0
    assert result.loc[1, "region"] == "Unknown"
    assert result["discount"].isna().sum() == 0
    assert result.loc[2, "discount"] == 0.025
    assert result["order_date"].isna().sum() == 0


def test_winsorize_clips_extreme_value_without_dropping_rows() -> None:
    values = pd.Series([10, 11, 12, 13, 1000])

    result = winsorize(values)

    assert len(result) == len(values)
    assert result.max() == 16


def test_remove_outliers_clips_price_and_quantity() -> None:
    df = pd.DataFrame(
        {
            "unit_price": [100, 110, 120, 130, 10_000],
            "quantity": [1, 2, 3, 4, 1000],
        }
    )
    original = df.copy(deep=True)

    result = remove_outliers(df)

    assert_frame_equal(df, original)
    assert len(result) == len(df)
    assert result["unit_price"].max() == 160
    assert result["quantity"].max() == 7
    assert pd.api.types.is_integer_dtype(result["quantity"])
