"""실습 4: Pandas 2.x 데이터 정제·집계와 Copy-on-Write 확인."""

from pathlib import Path
from typing import Optional

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "assets" / "sales_raw.csv"
UNKNOWN_REGION = "Unknown"

pd.options.mode.copy_on_write = True


def diagnose(df: pd.DataFrame, title: Optional[str] = None) -> None:
    """STEP 0: 정제 방향을 정하기 전에 타입·결측·분포를 진단한다."""
    print("=" * 50)
    print(f"[STEP 0] {title or '진단'}")
    print(f"shape: {df.shape}")
    print("\n-- dtypes --")
    print(df.dtypes)
    print("\n-- 결측치 개수 --")
    print(df.isna().sum())
    print("\n-- 수치형 요약 (이상치 냄새 확인) --")
    print(df[["quantity", "unit_price", "discount"]].describe())


def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    """STEP 1: 결측 처리 전에 숫자·날짜·범주 타입을 정규화한다."""
    result = df.copy()
    result["order_date"] = pd.to_datetime(result["order_date"], errors="coerce")
    for column in ("quantity", "unit_price", "discount"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["category"] = result["category"].astype("category")
    result["region"] = result["region"].astype("category")
    return result


def fill_missing(df: pd.DataFrame) -> pd.DataFrame:
    """STEP 2: 수치 결측은 카테고리 중앙값, 지역은 Unknown으로 대치한다."""
    result = df.copy()
    for column in ("quantity", "unit_price", "discount"):
        group_median = result.groupby("category", observed=True)[column].transform(
            "median"
        )
        result[column] = result[column].fillna(group_median)
        # 한 카테고리 전체가 결측인 경우에만 전체 중앙값을 fallback으로 사용한다.
        result[column] = result[column].fillna(result[column].median())

    if UNKNOWN_REGION not in result["region"].cat.categories:
        result["region"] = result["region"].cat.add_categories([UNKNOWN_REGION])
    result["region"] = result["region"].fillna(UNKNOWN_REGION)
    if result["order_date"].isna().any():
        result["order_date"] = result["order_date"].fillna(
            result["order_date"].dropna().median()
        )
    return result


def clean_price(df: pd.DataFrame) -> pd.DataFrame:
    """기존 테스트 호환용: 0 이하 가격도 결측으로 보고 그룹 중앙값으로 대치한다."""
    result = df.copy()
    result.loc[result["unit_price"] <= 0, "unit_price"] = pd.NA
    category_median = result.groupby("category", observed=True)[
        "unit_price"
    ].transform("median")
    result["unit_price"] = result["unit_price"].fillna(category_median)
    result["unit_price"] = result["unit_price"].fillna(
        result["unit_price"].median()
    )
    return result


def winsorize(series: pd.Series, k: float = 1.5) -> pd.Series:
    """IQR 경계 밖의 값을 삭제하지 않고 경곗값으로 조정한다."""
    q1, q3 = series.quantile([0.25, 0.75])
    iqr = q3 - q1
    low, high = q1 - k * iqr, q3 + k * iqr
    return series.clip(lower=low, upper=high)


def handle_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """STEP 3: IQR 윈저라이징 후 가격에는 0 이상이라는 도메인 규칙을 적용한다."""
    result = df.copy()
    result["quantity"] = winsorize(result["quantity"])
    result["unit_price"] = winsorize(result["unit_price"]).clip(lower=0)
    return result


def remove_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """기존 테스트와 호환되는 이상치 처리 함수."""
    result = handle_outliers(df)
    result["quantity"] = result["quantity"].round().astype("Int64")
    return result


def add_amount(df: pd.DataFrame) -> pd.DataFrame:
    """정제된 수량·가격·할인율로 매출액을 계산한다."""
    result = df.copy()
    result["amount"] = (
        result["quantity"] * result["unit_price"] * (1 - result["discount"])
    ).round()
    return result


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """정제 순서를 조율하며 각 단계의 세부 로직은 갖지 않는다."""
    result = normalize_types(df)
    result = fill_missing(result)
    result = handle_outliers(result)
    result = add_amount(result)
    return result


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """STEP 4: 카테고리별 건수·평균·중앙값·총매출을 집계한다."""
    return (
        df.groupby("category", observed=True)
        .agg(
            건수=("amount", "count"),
            평균매출=("amount", "mean"),
            중앙값매출=("amount", "median"),
            총매출=("amount", "sum"),
        )
        .round(1)
        .sort_values("총매출", ascending=False)
    )


def cross_tab(df: pd.DataFrame) -> pd.DataFrame:
    """STEP 5: 지역과 카테고리의 매출 교차표를 만든다."""
    return df.pivot_table(
        index="region",
        columns="category",
        values="amount",
        aggfunc="sum",
        fill_value=0,
        observed=True,
    )


def aggregate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """기존 호출 방식과 호환되는 집계 함수."""
    return summarize(df), cross_tab(df)


def merge_with_manager(df: pd.DataFrame) -> pd.DataFrame:
    """STEP 6: 지역 담당자를 left merge하고 행 수 보존을 검증한다."""
    managers = pd.DataFrame(
        {
            "region": ["Seoul", "Busan", "Incheon", "Daegu", "Gwangju"],
            "manager": ["김서울", "이부산", "박인천", "최대구", "정광주"],
        }
    )
    before = len(df)
    merged = df.merge(managers, on="region", how="left", validate="many_to_one")
    after = len(merged)
    assert after == before, (
        f"left merge 전후 행 수가 달라졌습니다: {before:,} -> {after:,}"
    )
    print(
        f"\n[STEP 6] merge 전후 행 수 : {before:,} -> {after:,} "
        f"(일치: {before == after})"
    )
    print("담당자 미배정(Unknown 지역 등) 건수:", merged["manager"].isna().sum())
    return merged


def demo_copy_on_write(df: pd.DataFrame) -> None:
    """STEP 7: 슬라이스 수정과 .loc 원본 수정을 대조한다."""
    print("\n" + "=" * 50)
    print("[STEP 7] Copy-on-Write 동작 확인")

    seoul_mask = df["region"] == "Seoul"
    original_first_amount = df.loc[seoul_mask, "amount"].iloc[0]

    # 슬라이스를 수정하면 CoW에 의해 원본 df는 바뀌지 않는다.
    seoul = df[seoul_mask]
    seoul["amount"] = seoul["amount"] * 1.1
    current_first_amount = df.loc[seoul_mask, "amount"].iloc[0]
    print(
        f"  슬라이스 수정 후 원본 첫 값 : {current_first_amount:,.0f} "
        f"(수정 전과 동일: {current_first_amount == original_first_amount})"
    )

    # 원본을 바꾸려면 체인 인덱싱 대신 .loc[조건, 컬럼]을 사용한다.
    df.loc[df["amount"] > 1_000_000, "flag"] = "high_value"
    high_value_count = (df["flag"] == "high_value").sum()
    print(f"  .loc 으로 원본에 flag 부여 : high_value {high_value_count:,}건")


def main() -> None:
    if not DATA_PATH.is_file():
        raise SystemExit(f"[오류] 데이터가 없습니다: {DATA_PATH}")

    raw = pd.read_csv(DATA_PATH)
    diagnose(raw)

    missing_before = (
        raw["region"].isna().sum()
        + pd.to_numeric(raw["unit_price"], errors="coerce").isna().sum()
    )
    price_max_before = pd.to_numeric(raw["unit_price"], errors="coerce").max()
    quantity_max_before = pd.to_numeric(raw["quantity"], errors="coerce").max()

    df = clean(raw)
    missing_after = df["region"].isna().sum() + df["unit_price"].isna().sum()

    print("\n" + "=" * 50)
    print("[정제 전후 비교]")
    print(
        f"  결측 개수(region+unit_price) : "
        f"{missing_before:,}건 -> {missing_after:,}건"
    )
    print(
        f"  unit_price max              : "
        f"{price_max_before:,.0f} -> {df['unit_price'].max():,.0f}"
    )
    print(
        f"  quantity max                : "
        f"{quantity_max_before:,.0f} -> {df['quantity'].max():,.0f}"
    )
    print(
        f"  dtypes 확인                 : order_date={df['order_date'].dtype}, "
        f"category={df['category'].dtype}"
    )

    print("\n" + "=" * 50)
    print("[STEP 4] 카테고리별 집계 (groupby.agg)")
    print(summarize(df))

    print("\n" + "=" * 50)
    print("[STEP 5] 지역 x 카테고리 교차표 (pivot_table)")
    print(cross_tab(df))

    merged = merge_with_manager(df)
    demo_copy_on_write(df)

    assert missing_after == 0, "결측이 남아있으면 안 됩니다"
    assert df["unit_price"].min() >= 0, "윈저라이징 후 음수 가격이 남았습니다"
    assert len(merged) == len(df), "merge 전후 행 수가 달라졌습니다"
    print(
        "\n[체크포인트 통과] 결측 0건 · 이상치 윈저라이징 완료 · "
        "merge 전후 행 수 일치"
    )


if __name__ == "__main__":
    main()
