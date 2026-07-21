"""readlines()로 웹 로그 전체를 메모리에 올린 뒤 집계하는 예제."""

import csv
from collections import Counter
from pathlib import Path
import tracemalloc

DATA_PATH = Path(__file__).resolve().parent / "web_logs.csv"


def aggregate(path: Path = DATA_PATH):
    # readlines()는 파일의 모든 줄을 리스트로 만들어 메모리에 저장한다.
    with path.open(encoding="utf-8") as file:
        lines = file.readlines()

    total = 0
    by_status = Counter()
    by_path = Counter()
    by_hour = Counter()
    by_ip = Counter()

    # DictReader는 문자열 리스트도 한 줄씩 읽을 수 있다.
    reader = csv.DictReader(lines)
    for row in reader:
        total += 1
        by_status[row["status"]] += 1
        by_path[row["path"]] += 1
        by_hour[row["timestamp"][11:13]] += 1
        by_ip[row["ip"]] += 1

    return total, by_status, by_path, by_hour, by_ip


def main() -> None:
    tracemalloc.start()
    total, by_status, by_path, by_hour, by_ip = aggregate()

    error_5xx = sum(
        count for status, count in by_status.items() if status.startswith("5")
    )
    error_ratio = error_5xx / total * 100 if total else 0.0

    print("=" * 40)
    print(f"총 요청 수: {total:,}")
    print(f"5xx 오류율: {error_ratio:.1f}% ({error_5xx:,}건)")

    print("-- 인기 경로 TOP 5 --")
    for path, count in by_path.most_common(5):
        print(f"  {path:<20} {count:>7,}")

    print("-- 시간대별 요청 --")
    for hour in sorted(by_hour):
        print(f"  {hour}시{'':<16} {by_hour[hour]:>7,}")

    print("-- 접속 상위 IP TOP 5 --")
    for ip, count in by_ip.most_common(5):
        print(f"  {ip:<20} {count:>7,}")

    # ... 집계 코드 실행 ...
    current, peak = tracemalloc.get_traced_memory()
    print(f"최대 메모리: {peak / 1024 / 1024:.2f} MB")
    tracemalloc.stop()


if __name__ == "__main__":
    main()
