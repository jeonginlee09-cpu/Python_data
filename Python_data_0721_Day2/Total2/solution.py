"""통신사 고객 이탈 분석: EDA -> 시각화 -> 통계 검정 -> 머신러닝."""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
import plotly.express as px
import plotly.io as pio
import polars as pl
from plotly.subplots import make_subplots
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "assets" / "telco_churn.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
REPORT_PATH = OUTPUT_DIR / "churn_report.html"
MODEL_PATH = OUTPUT_DIR / "churn_model.joblib"

TARGET = "churn"
ID_COLUMN = "customer_id"
NUMERIC_COLUMNS = [
    "senior",
    "tenure_months",
    "monthly_charges",
    "total_charges",
    "num_services",
]
CATEGORICAL_COLUMNS = ["gender", "contract", "payment_method"]


def load_data() -> pl.DataFrame:
    """CSV를 Polars DataFrame으로 읽고 필수 컬럼을 검증한다."""
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {INPUT_PATH}")

    df = pl.read_csv(INPUT_PATH, null_values=["", " ", "NA", "N/A", "null"])
    required = {
        ID_COLUMN,
        TARGET,
        *NUMERIC_COLUMNS,
        *CATEGORICAL_COLUMNS,
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {sorted(missing)}")
    return df


def run_eda(df: pl.DataFrame) -> None:
    """데이터 구조, 결측값, 타깃 비율과 이탈 그룹별 요약을 출력한다."""
    print("=== STEP 0 · EDA ===")
    print("shape:", df.shape)
    print("columns:", df.columns)
    print("schema:", dict(df.schema))
    print("\n[상위 5행]")
    print(df.head())
    print("\n[수치형 요약]")
    print(df.select(NUMERIC_COLUMNS).describe())
    print("\n[컬럼별 결측 개수]")
    print(df.null_count())

    churn_distribution = (
        df.group_by(TARGET)
        .len(name="count")
        .with_columns(
            (pl.col("count") / pl.col("count").sum() * 100)
            .round(2)
            .alias("ratio_pct")
        )
        .sort(TARGET)
    )
    print("\n[타깃 분포]")
    print(churn_distribution)

    churn_summary = (
        df.group_by(TARGET)
        .agg(
            pl.col("monthly_charges").mean().round(2).alias("avg_monthly_charges"),
            pl.col("tenure_months").mean().round(2).alias("avg_tenure_months"),
            pl.len().alias("customers"),
        )
        .sort(TARGET)
    )
    print("\n=== STEP 1 · 이탈 그룹과 잔류 그룹 비교 ===")
    print(churn_summary)


def create_report(pdf: pd.DataFrame) -> None:
    """요금 분포와 계약 유형별 이탈률을 하나의 Plotly HTML로 저장한다."""
    labeled = pdf.assign(
        churn_label=pdf[TARGET].map({0: "Retained", 1: "Churned"})
    )
    contract_rates = (
        labeled.groupby("contract", as_index=False, observed=True)[TARGET]
        .mean()
        .assign(churn_rate=lambda frame: frame[TARGET] * 100)
    )

    box = px.box(
        labeled,
        x="churn_label",
        y="monthly_charges",
        color="churn_label",
        points=False,
    )
    bar = px.bar(
        contract_rates,
        x="contract",
        y="churn_rate",
        color="contract",
    )
    report = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("이탈 여부별 월 요금 분포", "계약 유형별 이탈률"),
    )
    for trace in box.data:
        report.add_trace(trace, row=1, col=1)
    for trace in bar.data:
        report.add_trace(trace, row=1, col=2)
    report.update_yaxes(title_text="월 요금", row=1, col=1)
    report.update_yaxes(title_text="이탈률(%)", row=1, col=2)
    report.update_layout(
        title="통신사 고객 이탈 EDA 리포트",
        showlegend=False,
        template="plotly_white",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pio.write_html(report, REPORT_PATH, include_plotlyjs=True, auto_open=False)
    print("\n=== STEP 2 · 시각화 ===")
    print(f"Plotly HTML 저장: {REPORT_PATH}")


def run_statistical_tests(pdf: pd.DataFrame) -> tuple[float, float]:
    """월 요금 t-검정과 계약 유형-이탈 여부 카이제곱 검정을 수행한다."""
    churned = pdf.loc[pdf[TARGET] == 1, "monthly_charges"].dropna()
    retained = pdf.loc[pdf[TARGET] == 0, "monthly_charges"].dropna()
    t_stat, t_pvalue = stats.ttest_ind(churned, retained, equal_var=False)

    contingency = pd.crosstab(pdf["contract"], pdf[TARGET])
    chi2, chi_pvalue, dof, _ = stats.chi2_contingency(contingency)

    print("\n=== STEP 3 · 통계 검정 ===")
    print(f"Welch t-검정: t = {t_stat:.3f}, p = {t_pvalue:.2e}")
    print(f"카이제곱 검정: chi2 = {chi2:.3f}, dof = {dof}, p = {chi_pvalue:.2e}")
    print("해석: 요금 및 계약 유형은 이탈과 통계적으로 유의한 연관을 보입니다.")
    print("주의: 통계적 연관은 인과관계를 의미하지 않습니다.")
    return float(t_pvalue), float(chi_pvalue)


def build_pipeline() -> Pipeline:
    """결측 처리와 인코딩을 모델과 묶어 데이터 누수를 방지한다."""
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, NUMERIC_COLUMNS),
            ("categorical", categorical_pipeline, CATEGORICAL_COLUMNS),
        ]
    )
    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        n_jobs=-1,
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


def train_and_evaluate(pdf: pd.DataFrame) -> float:
    """계층 분할 후 Pipeline을 학습하고 ROC-AUC로 평가해 저장한다."""
    features = NUMERIC_COLUMNS + CATEGORICAL_COLUMNS
    X = pdf.loc[:, features]
    y = pdf[TARGET].astype("int8")
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    pipeline = build_pipeline()
    # 테스트셋을 보지 않고 train 내부 교차검증만으로 과적합 제어값을 고른다.
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    search = GridSearchCV(
        estimator=pipeline,
        param_grid={
            "model__max_depth": [5, 8, None],
            "model__min_samples_leaf": [2, 5, 10],
        },
        scoring="roc_auc",
        cv=cv,
        n_jobs=-1,
        refit=True,
    )
    search.fit(X_train, y_train)
    pipeline = search.best_estimator_
    probabilities = pipeline.predict_proba(X_test)[:, 1]
    predictions = pipeline.predict(X_test)
    auc = roc_auc_score(y_test, probabilities)

    print("\n=== STEP 4~7 · 전처리, 학습 및 평가 ===")
    print(f"train/test 크기: {len(X_train):,} / {len(X_test):,}")
    print(f"교차검증 최적 설정: {search.best_params_}")
    print(f"교차검증 ROC-AUC = {search.best_score_:.3f}")
    print(f"ROC-AUC = {auc:.3f}")
    print(classification_report(y_test, predictions, digits=3, zero_division=0))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    print(f"Pipeline 모델 저장: {MODEL_PATH}")
    return float(auc)


def main() -> None:
    # Windows 기본 콘솔에서도 Polars 표가 깨지지 않도록 ASCII 형식을 사용한다.
    pl.Config.set_tbl_formatting("ASCII_FULL")
    df = load_data()
    run_eda(df)

    # Plotly, SciPy, scikit-learn과의 연동을 위해 한 번만 Pandas로 변환한다.
    pdf = df.to_pandas()
    create_report(pdf)
    t_pvalue, chi_pvalue = run_statistical_tests(pdf)
    auc = train_and_evaluate(pdf)

    print("\n=== 성공 판정 ===")
    print(f"통계 검정 유의성(p < 0.05): {t_pvalue < 0.05 and chi_pvalue < 0.05}")
    print(f"ROC-AUC: {auc:.3f}")
    print(f"HTML 생성: {REPORT_PATH.is_file()}")
    print(f"모델 생성: {MODEL_PATH.is_file()}")


if __name__ == "__main__":
    main()
