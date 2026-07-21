"""비동기 ETL 파이프라인의 단계별 테스트 6개."""

import asyncio

import pandas as pd

from pipeline import extract, run, transform


def make_product(product_id: int = 1, **changes: object) -> dict[str, object]:
    """테스트 중복을 줄이는 정상 상품 생성 함수."""
    row: dict[str, object] = {
        "id": product_id,
        "name": "A",
        "category": "food",
        "price": 10.5,
    }
    row.update(changes)
    return row


def test_category_is_normalized_to_lowercase() -> None:
    valid, invalid = transform([make_product(category=" FOOD ")])

    assert valid[0].category == "food"
    assert invalid == []


def test_negative_price_is_rejected() -> None:
    valid, invalid = transform([make_product(price=-5)])

    assert valid == []
    assert len(invalid) == 1
    assert invalid[0]["data"]["price"] == -5


def test_transform_does_not_lose_rows() -> None:
    rows = [make_product(1), make_product(2), make_product(3, price=0)]
    valid, invalid = transform(rows)

    assert len(valid) + len(invalid) == len(rows)


def test_extract_limits_concurrency_and_retries() -> None:
    attempts: dict[int, int] = {}
    active = 0
    maximum_active = 0

    async def unstable_fetch(product_id: int) -> dict[str, object]:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        active -= 1

        attempts[product_id] = attempts.get(product_id, 0) + 1
        if product_id == 1 and attempts[product_id] == 1:
            raise RuntimeError("temporary")
        if product_id == 2:
            raise RuntimeError("permanent")
        return make_product(product_id)

    result = asyncio.run(
        extract(
            [1, 2, 3],
            max_concurrent=2,
            max_retries=2,
            fetcher=unstable_fetch,
            backoff_base=0,
        )
    )

    assert [row["id"] for row in result] == [1, 3]
    assert attempts == {1: 2, 2: 2, 3: 1}
    assert maximum_active <= 2


def test_parquet_round_trip(tmp_path) -> None:
    original = pd.DataFrame({"id": [1, 2], "price": [10.5, 20.0]})
    parquet_path = tmp_path / "test.parquet"

    original.to_parquet(parquet_path, index=False)
    restored = pd.read_parquet(parquet_path)

    pd.testing.assert_frame_equal(original, restored)


def test_run_orchestrates_etl_and_saves_files(tmp_path) -> None:
    async def fake_fetch(product_id: int) -> dict[str, object]:
        price = -1 if product_id == 2 else 10
        return make_product(product_id, category=" BOOK ", price=price)

    summary = asyncio.run(run([1, 2, 3], tmp_path, fetcher=fake_fetch))

    assert summary == {"total": 3, "valid": 2, "invalid": 1, "rows_saved": 2}
    assert (tmp_path / "products.csv").exists()
    assert (tmp_path / "products.parquet").exists()
    saved = pd.read_parquet(tmp_path / "products.parquet")
    assert saved["category"].tolist() == ["book", "book"]
