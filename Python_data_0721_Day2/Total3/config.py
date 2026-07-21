from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]


# 실행 중 변경할 수 없는 리포트 설정
@dataclass(frozen=True)
class Config:
    data_path: Path
    output_dir: Path
    template_dir: Path
    title: str = "일일 매출 리포트"
    top_n: int = 10


CONFIG = Config(
    data_path=REPO_ROOT / "Python_data_0720_Day1" / "data" / "sales_raw.csv",
    output_dir=BASE_DIR / "output",
    template_dir=BASE_DIR / "templates",
)
