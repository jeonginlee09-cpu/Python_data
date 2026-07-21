"""
공용 샘플 데이터 생성기
========================
모든 실습이 외부 네트워크 없이 재현 가능하도록, 결정적(seed 고정) 합성
데이터를 생성한다. 실제 현장 데이터와 유사한 '지저분함'(결측치, 이상치,
타입 불일치, 스키마 변형)을 의도적으로 주입하여 전처리 실습의 난이도를
'중상' 수준으로 맞춘다.

실행:
    python data/generate_data.py

산출물(data/ 디렉터리):
    web_logs.csv        : 실습1 - 대용량 웹 접근 로그 (스트리밍 집계용)
    api_response.json   : 실습2 - 중첩 스키마 API 응답 (Pydantic 검증용)
    sales_raw.csv       : 실습4 - 결측/이상치 포함 판매 데이터 (Pandas 클리닝)
    events_large.csv    : 실습5 - 대용량 이벤트 데이터 (Polars/DuckDB)
    telco_churn.csv     : 종합2 - 이탈 예측용 통합 데이터셋 (EDA + ML)
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
SEED = 42
random.seed(SEED)


def _ts_range(n: int, start: datetime) -> list[datetime]:
    """start부터 초 단위로 무작위 증가하는 타임스탬프 시퀀스."""
    cur = start
    out = []
    for _ in range(n):
        cur += timedelta(seconds=random.randint(0, 5))
        out.append(cur)
    return out


def gen_web_logs(n: int = 200_000) -> None:
    """실습1: Apache-combined 유사 웹 로그. 라인 단위 스트리밍 집계 대상."""
    paths = ["/", "/products", "/products/detail", "/cart", "/checkout",
             "/login", "/api/v1/search", "/api/v1/items", "/static/app.js", "/health"]
    methods = ["GET"] * 8 + ["POST"] * 2
    statuses = [200] * 80 + [301, 302, 404, 500, 503] * 4
    uas = ["Mozilla/5.0 (Windows NT 10.0)", "Mozilla/5.0 (Macintosh)",
           "curl/8.4.0", "python-httpx/0.27.2", "Googlebot/2.1"]
    start = datetime(2025, 3, 1, 0, 0, 0)
    tss = _ts_range(n, start)

    out = DATA_DIR / "web_logs.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ip", "timestamp", "method", "path", "status", "bytes", "user_agent"])
        for i in range(n):
            ip = f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
            w.writerow([
                ip,
                tss[i].strftime("%Y-%m-%dT%H:%M:%S"),
                random.choice(methods),
                random.choice(paths),
                random.choice(statuses),
                random.randint(120, 250_000),
                random.choice(uas),
            ])
    print(f"[web_logs.csv] {n:,} rows -> {out}")


def gen_api_response() -> None:
    """실습2: 중첩 구조 + 일부 오염 레코드를 포함한 API 응답."""
    users = []
    for uid in range(1, 41):
        rec = {
            "id": uid,
            "username": f"user_{uid:03d}",
            "email": f"user{uid}@example.com",
            "age": random.randint(18, 72),
            "is_active": random.choice([True, False]),
            "signup_date": (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 500))).strftime("%Y-%m-%d"),
            "profile": {
                "country": random.choice(["KR", "US", "JP", "DE"]),
                "tier": random.choice(["free", "pro", "enterprise"]),
                "score": round(random.uniform(0, 100), 2),
            },
            "tags": random.sample(["ai", "data", "web", "cloud", "mobile"], k=random.randint(0, 3)),
        }
        # 의도적 오염: 검증 실패 유도 (음수 나이, 잘못된 이메일, 누락 필드)
        if uid == 7:
            rec["age"] = -5
        if uid == 13:
            rec["email"] = "not-an-email"
        if uid == 21:
            del rec["email"]
        if uid == 29:
            rec["profile"]["score"] = 150.0  # 0~100 범위 초과
        users.append(rec)

    payload = {"status": "ok", "count": len(users), "results": users}
    out = DATA_DIR / "api_response.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[api_response.json] {len(users)} records (4 corrupted) -> {out}")


def gen_sales_raw(n: int = 5_000) -> None:
    """실습4: 결측치·이상치·타입불일치를 포함한 판매 데이터."""
    regions = ["Seoul", "Busan", "Incheon", "Daegu", "Gwangju"]
    categories = ["Electronics", "Fashion", "Home", "Beauty", "Food"]
    out = DATA_DIR / "sales_raw.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["order_id", "order_date", "region", "category", "quantity", "unit_price", "discount"])
        base = datetime(2025, 1, 1)
        for i in range(n):
            qty = random.randint(1, 10)
            price = round(random.uniform(5_000, 300_000), 0)
            disc = round(random.choice([0, 0, 0, 0.05, 0.1, 0.15]), 2)
            # 결측치 주입 (약 6%)
            region = random.choice(regions) if random.random() > 0.06 else ""
            price_out = "" if random.random() < 0.04 else price
            # 이상치 주입 (약 1%) : 비정상적으로 큰 수량/음수 가격
            if random.random() < 0.01:
                qty = random.randint(500, 2000)
            if random.random() < 0.005:
                price_out = -abs(price)
            w.writerow([
                f"ORD-{i:06d}",
                (base + timedelta(days=random.randint(0, 120))).strftime("%Y-%m-%d"),
                region,
                random.choice(categories),
                qty,
                price_out,
                disc,
            ])
    print(f"[sales_raw.csv] {n:,} rows (with missing/outliers) -> {out}")


def gen_events_large(n: int = 1_000_000) -> None:
    """실습5: Polars/DuckDB 대용량 처리용 이벤트 스트림."""
    out = DATA_DIR / "events_large.csv"
    event_types = ["view", "click", "add_to_cart", "purchase", "refund"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["event_id", "user_id", "event_type", "ts", "amount"])
        base = datetime(2025, 1, 1)
        for i in range(n):
            et = random.choices(event_types, weights=[50, 30, 12, 6, 2])[0]
            amount = round(random.uniform(1_000, 500_000), 0) if et in ("purchase", "refund") else 0
            w.writerow([
                i,
                random.randint(1, 50_000),
                et,
                (base + timedelta(seconds=random.randint(0, 90 * 86400))).strftime("%Y-%m-%d %H:%M:%S"),
                amount,
            ])
    print(f"[events_large.csv] {n:,} rows -> {out}")


def gen_telco_churn(n: int = 7_000) -> None:
    """종합2: 이탈 예측용 통합 데이터셋 (범주형+수치형+결측+타깃)."""
    out = DATA_DIR / "telco_churn.csv"
    contracts = ["Month-to-month", "One year", "Two year"]
    payments = ["Electronic check", "Mailed check", "Bank transfer", "Credit card"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["customer_id", "gender", "senior", "tenure_months", "monthly_charges",
                    "total_charges", "contract", "payment_method", "num_services", "churn"])
        for i in range(n):
            tenure = random.randint(0, 72)
            monthly = round(random.uniform(18, 120), 2)
            total = round(monthly * tenure * random.uniform(0.9, 1.1), 2) if tenure else 0.0
            contract = random.choice(contracts)
            # 이탈 확률: 단기계약·고요금·저근속에서 상승 (신호를 인위적으로 주입)
            base_p = 0.12
            if contract == "Month-to-month":
                base_p += 0.22
            if monthly > 90:
                base_p += 0.12
            if tenure < 6:
                base_p += 0.18
            churn = 1 if random.random() < min(base_p, 0.9) else 0
            total_out = "" if random.random() < 0.02 else total  # 결측 2%
            w.writerow([
                f"CUST-{i:05d}",
                random.choice(["Male", "Female"]),
                random.choice([0, 0, 0, 1]),
                tenure,
                monthly,
                total_out,
                contract,
                random.choice(payments),
                random.randint(1, 8),
                churn,
            ])
    print(f"[telco_churn.csv] {n:,} rows -> {out}")


if __name__ == "__main__":
    print("샘플 데이터 생성 시작 (seed=42, 결정적)...")
    gen_web_logs()
    gen_api_response()
    gen_sales_raw()
    gen_events_large()
    gen_telco_churn()
    print("완료. data/ 디렉터리를 확인하십시오.")
