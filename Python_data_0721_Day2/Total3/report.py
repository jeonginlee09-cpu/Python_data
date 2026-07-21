from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ============================================================
# 1. 매출 데이터 정제
# ============================================================


# 원본을 변경하지 않고 가격·수량 결측치와 이상치를 정제
def prepare_sales(df):
    required = {"order_id", "category", "quantity", "unit_price"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {sorted(missing)}")

    result = df.copy()
    result["quantity"] = pd.to_numeric(result["quantity"], errors="coerce")
    result["unit_price"] = pd.to_numeric(result["unit_price"], errors="coerce")
    result["unit_price"] = result.groupby("category", observed=True)[
        "unit_price"
    ].transform(lambda values: values.fillna(values.median()))

    # IQR 경계 밖의 가격과 수량을 삭제하지 않고 경계값으로 조정
    for column in ["unit_price", "quantity"]:
        q1, q3 = result[column].quantile([0.25, 0.75])
        iqr = q3 - q1
        result[column] = result[column].clip(
            lower=q1 - 1.5 * iqr,
            upper=q3 + 1.5 * iqr,
        )

    result["amount"] = result["quantity"] * result["unit_price"]
    if result[["category", "quantity", "unit_price", "amount"]].isna().any().any():
        raise ValueError("리포트 집계에 필요한 데이터에 결측치가 남았습니다.")
    return result


# ============================================================
# 2. 리포트 데이터 집계
# ============================================================


# DataFrame만 받아 KPI와 카테고리별 매출을 만드는 순수 함수
def aggregate(df, top_n=10):
    if top_n < 1:
        raise ValueError("top_n은 1 이상이어야 합니다.")
    if "amount" not in df.columns:
        raise ValueError("집계에 필요한 amount 컬럼이 없습니다.")

    by_category = (
        df.groupby("category", observed=True)["amount"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .reset_index()
    )
    return {
        "kpi": {
            "총매출": round(df["amount"].sum()),
            "주문수": len(df),
            "평균 주문액": round(df["amount"].mean(), 1),
        },
        "by_category": by_category.to_dict("records"),
    }


# ============================================================
# 3. Jinja2 HTML 렌더링
# ============================================================


# 집계 결과를 별도 템플릿으로 렌더링해 타임스탬프 파일로 저장
def render(data, config, now=None):
    generated_at = now or datetime.now()
    environment = Environment(
        loader=FileSystemLoader(config.template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("report.html")
    html = template.render(
        title=config.title,
        generated_at=generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        **data,
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%d_%H%M%S_%f")
    output_path = Path(config.output_dir) / f"report_{stamp}.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path
