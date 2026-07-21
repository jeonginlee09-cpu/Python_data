"""실습 5: Pandas, Polars Lazy API, DuckDB 성능 비교."""

from __future__ import annotations

import statistics
import time
from pathlib import Path
from typing import Callable, TypeVar

import duckdb
import pandas as pd
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "assets" / "events_large.csv"
BENCHMARK_RUNS = 3

T = TypeVar("T")


def timed_run(func: Callable[[], T]) -> tuple[T, float]:
    """파일 읽기부터 결과 생성까지 실행하고 경과 시간을 ms로 반환한다."""
    start = time.perf_counter()
    result = func()
    elapsed_ms = (time.perf_counter() - start) * 1_000
    return result, elapsed_ms


def run_pandas() -> pd.DataFrame:
    """Pandas로 양수 금액의 event_type별 건수와 평균을 계산한다."""
    df = pd.read_csv(INPUT_PATH)
    return (
        df.loc[df["amount"] > 0]
        .groupby("event_type", as_index=False)
        .agg(cnt=("amount", "count"), avg=("amount", "mean"))
        .sort_values("cnt", ascending=False)
        .reset_index(drop=True)
    )


def polars_query() -> pl.LazyFrame:
    """실행 전 최적화가 가능한 Polars Lazy 질의 계획을 만든다."""
    return (
        pl.scan_csv(INPUT_PATH)
        .filter(pl.col("amount") > 0)
        .group_by("event_type")
        .agg(
            pl.col("amount").count().alias("cnt"),
            pl.col("amount").mean().alias("avg"),
        )
        .sort("cnt", descending=True)
    )


def run_polars() -> pl.DataFrame:
    """Lazy 질의를 collect하여 실제로 실행한다."""
    return polars_query().collect()


def run_duckdb() -> pd.DataFrame:
    """DuckDB SQL로 CSV 파일을 직접 조회한다."""
    path = INPUT_PATH.as_posix().replace("'", "''")
    query = f"""
        SELECT
            event_type,
            COUNT(amount) AS cnt,
            AVG(amount) AS avg
        FROM read_csv_auto('{path}')
        WHERE amount > 0
        GROUP BY event_type
        ORDER BY cnt DESC
    """
    return duckdb.sql(query).df()


def benchmark(
    name: str, func: Callable[[], T], runs: int = BENCHMARK_RUNS
) -> tuple[T, float, list[float]]:
    """같은 작업을 반복하고 대표 실행 시간으로 중앙값을 사용한다."""
    result: T | None = None
    times: list[float] = []

    for run in range(1, runs + 1):
        result, elapsed_ms = timed_run(func)
        times.append(elapsed_ms)
        print(f"{name} {run}회차: {elapsed_ms:,.0f} ms")

    assert result is not None
    median_ms = statistics.median(times)
    print(f"{name} 중앙값: {median_ms:,.0f} ms\n")
    return result, median_ms, times


def normalized(result: pd.DataFrame) -> pd.DataFrame:
    """비교 전에 엔진별 컬럼·정렬·인덱스·데이터 타입을 통일한다."""
    normalized_result = (
        result.loc[:, ["event_type", "cnt", "avg"]]
        .sort_values("event_type")
        .reset_index(drop=True)
    )
    return normalized_result.astype(
        {"event_type": "string", "cnt": "int64", "avg": "float64"}
    )


def validate_results(
    pandas_result: pd.DataFrame,
    polars_result: pl.DataFrame,
    duckdb_result: pd.DataFrame,
) -> None:
    """정렬·타입·컬럼 순서를 통일한 뒤 세 엔진 결과를 검증한다."""
    expected = normalized(pandas_result)
    actual_polars = normalized(polars_result.to_pandas())
    actual_duckdb = normalized(duckdb_result)

    # 평균은 엔진별 부동소수점 계산에서 미세한 차이가 날 수 있으므로 허용 오차를 둔다.
    pd.testing.assert_frame_equal(
        expected, actual_polars, check_dtype=False, atol=1e-6
    )
    pd.testing.assert_frame_equal(
        expected, actual_duckdb, check_dtype=False, atol=1e-6
    )
    print("✅ 세 엔진 결과 일치!\n")


def print_benchmark_table(times: dict[str, float]) -> None:
    """Pandas를 기준선으로 실행 시간과 배속을 출력한다."""
    pandas_time = times["Pandas"]
    print(f"{'엔진':<10}{'시간(ms)':>12}{'Pandas 대비':>14}")
    print("-" * 36)
    for name, elapsed_ms in sorted(times.items(), key=lambda item: item[1]):
        print(f"{name:<10}{elapsed_ms:>12,.0f}{pandas_time / elapsed_ms:>13.1f}x")

    observed_order = " < ".join(
        name for name, _ in sorted(times.items(), key=lambda item: item[1])
    )
    print(f"\n관측된 속도 순서: {observed_order}")


def main() -> None:
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {INPUT_PATH}")

    print("=== 실습 5: Pandas · Polars · DuckDB 성능 비교 ===")
    print(f"입력 파일: {INPUT_PATH}")
    print(f"파일 크기: {INPUT_PATH.stat().st_size / 1024**2:,.1f} MB")
    print(f"반복 횟수: 엔진별 {BENCHMARK_RUNS}회 (중앙값 사용)\n")
    print("질의: amount > 0인 행을 event_type별로 묶어 건수와 평균 계산\n")

    print("=== Polars 최적화 실행 계획 ===")
    print(polars_query().explain(optimized=True))
    print()

    pandas_result, pandas_ms, _ = benchmark("Pandas", run_pandas)
    polars_result, polars_ms, _ = benchmark("Polars", run_polars)
    duckdb_result, duckdb_ms, _ = benchmark("DuckDB", run_duckdb)

    print("=== 집계 결과 예시 ===")
    print(pandas_result.head(), "\n")

    print("=== 결과 일치 검증 ===")
    validate_results(pandas_result, polars_result, duckdb_result)

    print("=== 실행 시간 비교 ===")
    print_benchmark_table(
        {"Pandas": pandas_ms, "Polars": polars_ms, "DuckDB": duckdb_ms}
    )


if __name__ == "__main__":
    main()
