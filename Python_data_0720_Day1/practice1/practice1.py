"""대용량 웹 로그를 한 번만 순회하여 요약 지표를 계산한다."""

from __future__ import annotations

import csv
from collections import Counter
from functools import reduce
from pathlib import Path
from typing import Iterator

import tracemalloc


DATA_PATH = Path(__file__).resolve().parent / "web_logs.csv"


def read_logs(path: Path) -> Iterator[dict[str, str]]:
    """CSV 파일을 한 행씩 읽어 반환하는 제너레이터."""
    with path.open(newline="", encoding="utf-8") as file:
        r = csv.DictReader(file)
        for row in r:
            yield row


def fold(acc: dict[str, int | Counter[str]], row: dict[str, str]):
    """로그 한 행을 누적 집계 결과에 반영한다."""
    status = row["status"]
    timestamp = row["timestamp"]

    acc["total"] += 1
    acc["status"][status] += 1
    acc["path"][row["path"]] += 1
    acc["hour"][timestamp[11:13]] += 1
    acc["ip"][row["ip"]] += 1
    return acc


def aggregate(path: Path = DATA_PATH):
    """로그 파일을 한 번만 순회해 필요한 모든 지표를 집계한다."""
    initial = {
        "total": 0,
        "status": Counter(),
        "path": Counter(),
        "hour": Counter(),
        "ip": Counter(),
    }
    return reduce(fold, read_logs(path), initial)


def print_top(title: str, counter: Counter[str], limit: int = 5) -> None:
    print(title)
    for value, count in counter.most_common(limit):
        print(f"  {value:<20} {count:>7,}")


def print_hourly(counter: Counter[str]) -> None:
    print("-- 시간대별 요청 --")
    for hour in sorted(counter):
        print(f"  {hour}시{'':<16} {counter[hour]:>7,}")


def main() -> None:
    tracemalloc.start()

    result = aggregate()

    total = result["total"]
    error_5xx = sum(
        count for status, count in result["status"].items() if status.startswith("5")
    )
    error_ratio = error_5xx / total * 100 if total else 0.0

    print("=" * 40)
    print(f"총 요청 수: {total:,}")
    print(f"5xx 오류율: {error_ratio:.1f}% ({error_5xx:,}건)")
    print_top("-- 인기 경로 TOP 5 --", result["path"])
    print_hourly(result["hour"])
    print_top("-- 접속 상위 IP TOP 5 --", result["ip"])

    # ... 집계 코드 실행 ...
    current, peak = tracemalloc.get_traced_memory()
    print(f"최대 메모리: {peak / 1024 / 1024:.2f} MB")
    tracemalloc.stop()


if __name__ == "__main__":
    main()
