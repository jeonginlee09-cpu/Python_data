# ============================================================
# 작성자: 김규진
# 작성목적: [Total3] 분석 자동화·HTML 리포트 생성
# 작성일: 2026-07-20
#
# 변경사항 내역
# - 날짜: 2026-07-20
#   변경목적: [Total3] 일일 매출 리포트 자동화 구현
#   변경내용: 단발·경량 루프·schedule·cron 실행 방식이
#           동일한 run_once 함수를 호출하도록 구성
# ============================================================

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import schedule

<<<<<<< HEAD
try:
    from Python_data_0721_Day2.Total3.config import CONFIG
    from Python_data_0721_Day2.Total3.report import aggregate, prepare_sales, render
except ModuleNotFoundError:
    from Python_data_0721_Day2.Total3.config import CONFIG
    from Python_data_0721_Day2.Total3.report import aggregate, prepare_sales, render
=======
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Python_data_0721_Day2.Total3.config import CONFIG
from Python_data_0721_Day2.Total3.report import aggregate, prepare_sales, render
>>>>>>> 82aec07 (과제 수행일에 따른 계층 구조 분리)

# ============================================================
# 1. 공통 단발 실행 함수
# ============================================================


# 모든 실행 방식이 공유하는 동일한 분석·렌더링 과정
def run_once(config=CONFIG):
    raw = pd.read_csv(config.data_path)
    cleaned = prepare_sales(raw)
    report_data = aggregate(cleaned, top_n=config.top_n)
    output_path = render(report_data, config)

    print(f"리포트 생성: {output_path}")
    return output_path


# ============================================================
# 2. 경량 반복 실행
# ============================================================


# 지정한 초 간격으로 같은 run_once 함수를 반복 호출
def run_loop(interval, config=CONFIG):
    if interval <= 0:
        raise ValueError("반복 실행 간격은 1초 이상이어야 합니다.")

    print(f"{interval}초 간격으로 실행합니다. 종료하려면 Ctrl+C를 누르세요.")
    while True:
        run_once(config)
        time.sleep(interval)


# ============================================================
# 3. schedule 선언적 실행
# ============================================================


# 매일 지정한 시각에 동일한 run_once 함수를 실행
def run_daily(daily_at, config=CONFIG):
    try:
        time.strptime(daily_at, "%H:%M")
    except ValueError as error:
        raise ValueError("실행 시각은 HH:MM 형식이어야 합니다.") from error

    schedule.clear()
    schedule.every().day.at(daily_at).do(run_once, config=config)
    print(f"매일 {daily_at}에 실행합니다. 종료하려면 Ctrl+C를 누르세요.")

    while True:
        schedule.run_pending()
        time.sleep(1)


# ============================================================
# 4. 실행 옵션 처리
# ============================================================


# 단발, 초 단위 반복과 일일 스케줄 옵션 정의
def parse_args():
    parser = argparse.ArgumentParser(description="일일 매출 리포트 자동화")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--interval",
        type=int,
        default=0,
        help="초 단위 반복 간격. 0이면 한 번만 실행",
    )
    group.add_argument(
        "--daily-at",
        metavar="HH:MM",
        help="schedule 방식의 매일 실행 시각",
    )
    return parser.parse_args()


# CLI 옵션에 따라 실행하되 모든 방식에서 run_once를 재사용
def main():
    args = parse_args()

    try:
        if args.daily_at:
            run_daily(args.daily_at)
        elif args.interval > 0:
            run_loop(args.interval)
        elif args.interval == 0:
            run_once()
        else:
            raise ValueError("--interval은 0 이상의 정수여야 합니다.")
    except KeyboardInterrupt:
        print("\n리포트 자동 실행을 종료합니다.")


if __name__ == "__main__":
    main()
