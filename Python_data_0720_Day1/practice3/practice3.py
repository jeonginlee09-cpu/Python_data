"""Semaphore와 재시도를 적용한 asyncio 기반 비동기 수집기."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any


USE_REAL_HTTP = False
TOTAL_ITEMS = 60
MAX_CONCURRENT = 10
REQUEST_TIMEOUT = 3.0
MAX_RETRIES = 3
BACKOFF_BASE = 0.2
MOCK_DELAY = 0.21

DEAD_LETTER_PATH = Path(__file__).resolve().parent / "dead_letter.json"
PERMANENT_FAILURE_IDS = {17, 43}

# 모의 요청이 항목별로 몇 번 실행됐는지 기록한다.
attempt_counts: dict[int, int] = {}


class TemporaryRequestError(Exception):
    """재시도하면 성공할 수 있는 일시적인 요청 오류."""


async def mock_request(item_id: int) -> dict[str, Any]:
    """네트워크 지연과 일시 장애를 재현하는 모의 요청."""
    await asyncio.sleep(MOCK_DELAY)
    attempt_counts[item_id] = attempt_counts.get(item_id, 0) + 1

    # dead-letter 격리를 확인하기 위해 모든 재시도에서 실패하게 한다.
    if item_id in PERMANENT_FAILURE_IDS:
        raise TemporaryRequestError("모의 영구 서버 오류")

    # 네 항목은 첫 시도에만 실패해 재시도 동작을 확인할 수 있다.
    if item_id in {13, 26, 39, 52} and attempt_counts[item_id] == 1:
        raise TemporaryRequestError("모의 일시적 서버 오류")

    return {"id": item_id, "ok": True, "source": "mock"}


async def real_http_request(item_id: int, client: Any) -> dict[str, Any]:
    """공개 테스트 API에서 한 항목을 가져온다."""
    url = f"https://jsonplaceholder.typicode.com/todos/{item_id}"
    response = await client.get(url)
    response.raise_for_status()
    return {
        "id": item_id,
        "ok": True,
        "source": "http",
        "data": response.json(),
    }


async def do_request(item_id: int, client: Any = None) -> dict[str, Any]:
    """설정에 따라 모의 요청 또는 실제 HTTP 요청을 수행한다."""
    if USE_REAL_HTTP:
        return await real_http_request(item_id, client)
    return await mock_request(item_id)


async def fetch_with_retry(
    item_id: int,
    semaphore: asyncio.Semaphore,
    client: Any = None,
) -> dict[str, Any]:
    """동시성 제한, 타임아웃, 지수 백오프를 적용해 한 건을 수집한다."""
    for attempt in range(MAX_RETRIES):
        try:
            # 요청 중에만 입장권을 점유한다. 백오프 중에는 반납한다.
            async with semaphore:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    return await do_request(item_id, client)
        except Exception as error:
            if attempt == MAX_RETRIES - 1:
                return {
                    "id": item_id,
                    "ok": False,
                    "error": type(error).__name__,
                    "reason": str(error),
                    "attempts": MAX_RETRIES,
                }

            wait_seconds = BACKOFF_BASE * (2**attempt)
            print(
                f"[{item_id:02d}] {type(error).__name__}: "
                f"{wait_seconds:.1f}초 후 재시도"
            )
            await asyncio.sleep(wait_seconds)

    raise RuntimeError("도달할 수 없는 코드")


async def collect(client: Any = None) -> list[dict[str, Any]]:
    """60개 작업을 예약하고, 한 작업의 예외가 전체로 번지지 않게 수집한다."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [
        fetch_with_retry(item_id, semaphore, client)
        for item_id in range(1, TOTAL_ITEMS + 1)
    ]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[dict[str, Any]] = []
    for item_id, result in enumerate(gathered, start=1):
        if isinstance(result, BaseException):
            results.append(
                {
                    "id": item_id,
                    "ok": False,
                    "error": type(result).__name__,
                    "reason": str(result),
                }
            )
        else:
            results.append(result)
    return results


async def main() -> list[dict[str, Any]]:
    """필요할 때만 httpx를 불러오고 연결 풀 하나를 모든 요청이 공유한다."""
    attempt_counts.clear()

    if not USE_REAL_HTTP:
        return await collect()

    try:
        import httpx
    except ImportError as error:
        raise RuntimeError(
            "실제 HTTP 모드에는 httpx가 필요합니다: "
            "python -m pip install -r practice3/requirements.txt"
        ) from error

    async with httpx.AsyncClient() as client:
        return await collect(client)


def save_dead_letters(
    results: list[dict[str, Any]],
    path: Path = DEAD_LETTER_PATH,
) -> list[dict[str, Any]]:
    """최종 실패 항목을 원인 분석과 재처리용 JSON 파일에 저장한다."""
    failed = [item for item in results if not item["ok"]]
    path.write_text(
        json.dumps(failed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return failed


if __name__ == "__main__":
    started_at = time.perf_counter()
    collected = asyncio.run(main())
    elapsed = time.perf_counter() - started_at

    dead_letters = save_dead_letters(collected)
    success_count = sum(item["ok"] for item in collected)
    print(
        f"전체 {len(collected)}건 / 성공 {success_count}건 / "
        f"실패 {len(dead_letters)}건 / {elapsed:.2f}초"
    )
    print(f"dead-letter {len(dead_letters)}건 저장: {DEAD_LETTER_PATH}")
