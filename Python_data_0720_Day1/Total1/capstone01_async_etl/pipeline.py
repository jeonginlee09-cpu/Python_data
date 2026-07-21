"""실습 2와 실습 3을 결합한 비동기 ETL 파이프라인."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from models import Product

TOTAL_ITEMS = 60
MAX_CONCURRENT = 10
MAX_RETRIES = 3
REQUEST_TIMEOUT = 3.0
BACKOFF_BASE = 0.2
MOCK_DELAY = 0.02
PERMANENT_FAILURE_IDS = {17, 43}
TRANSIENT_FAILURE_IDS = {13, 26, 39, 52}
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"

Fetcher = Callable[[int], Awaitable[dict[str, Any]]]
attempt_counts: dict[int, int] = {}


class TemporaryRequestError(Exception):
    """재시도로 복구될 수 있는 모의 요청 오류."""


async def fetch(product_id: int) -> dict[str, Any]:
    """실습 3의 장애 상황을 재현하면서 모의 상품 한 건을 가져온다."""
    await asyncio.sleep(MOCK_DELAY)
    attempt_counts[product_id] = attempt_counts.get(product_id, 0) + 1

    if product_id in PERMANENT_FAILURE_IDS:
        raise TemporaryRequestError("모의 영구 서버 오류")
    if product_id in TRANSIENT_FAILURE_IDS and attempt_counts[product_id] == 1:
        raise TemporaryRequestError("모의 일시적 서버 오류")

    categories = (" FOOD ", "Book", "ELECTRONICS")
    return {
        "id": product_id,
        "name": f"Product {product_id}",
        "category": categories[product_id % len(categories)],
        "price": round(product_id * 1.25, 2),
    }


async def extract(
    ids: Sequence[int],
    max_concurrent: int = MAX_CONCURRENT,
    max_retries: int = MAX_RETRIES,
    fetcher: Fetcher = fetch,
    backoff_base: float = BACKOFF_BASE,
) -> list[dict[str, Any]]:
    """동시성 제한, 타임아웃, 지수 백오프 재시도로 데이터를 추출한다."""
    if max_concurrent < 1:
        raise ValueError("max_concurrent는 1 이상이어야 합니다")
    if max_retries < 1:
        raise ValueError("max_retries는 1 이상이어야 합니다")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def extract_one(product_id: int) -> dict[str, Any]:
        for attempt in range(max_retries):
            try:
                # 실습 3처럼 요청 중에만 세마포어를 점유한다.
                async with semaphore:
                    async with asyncio.timeout(REQUEST_TIMEOUT):
                        return await fetcher(product_id)
            except Exception:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(backoff_base * (2**attempt))
        raise RuntimeError("도달할 수 없는 코드")

    results = await asyncio.gather(
        *(extract_one(product_id) for product_id in ids),
        return_exceptions=True,
    )
    # 한 건의 최종 실패가 전체 수집을 중단시키지 않는다.
    return [result for result in results if not isinstance(result, BaseException)]


def transform(
    raw: Sequence[dict[str, Any]],
) -> tuple[list[Product], list[dict[str, Any]]]:
    """입력만 계산하고 외부를 건드리지 않는 순수 Transform 함수."""
    valid: list[Product] = []
    invalid: list[dict[str, Any]] = []

    for row in raw:
        try:
            valid.append(Product.model_validate(row))
        except ValidationError as error:
            invalid.append({"data": row, "errors": error.errors(include_url=False)})
    return valid, invalid


def load(
    valid: Sequence[Product],
    out_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> pd.DataFrame:
    """유효 상품을 DataFrame, CSV, Parquet으로 적재한다."""
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame([product.model_dump() for product in valid])
    frame.to_csv(output_dir / "products.csv", index=False)
    frame.to_parquet(output_dir / "products.parquet", index=False)
    return frame


async def run(
    ids: Sequence[int],
    out_dir: str | Path = DEFAULT_OUTPUT_DIR,
    fetcher: Fetcher = fetch,
) -> dict[str, int]:
    """직접 처리하지 않고 Extract, Transform, Load만 순서대로 조율한다."""
    raw = await extract(ids, fetcher=fetcher)
    valid, invalid = transform(raw)
    frame = load(valid, out_dir)
    return {
        "total": len(raw),
        "valid": len(valid),
        "invalid": len(invalid),
        "rows_saved": len(frame),
    }


if __name__ == "__main__":
    attempt_counts.clear()
    summary = asyncio.run(run(range(1, TOTAL_ITEMS + 1)))
    print(summary)
