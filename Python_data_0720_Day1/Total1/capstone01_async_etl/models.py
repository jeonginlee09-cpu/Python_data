"""ETL Transform 단계에서 사용하는 Pydantic 모델."""

from pydantic import BaseModel, Field, field_validator


class Product(BaseModel):
    """수집한 상품 한 건의 스키마."""

    id: int
    name: str
    category: str
    price: float = Field(gt=0)

    @field_validator("category")
    @classmethod
    def lower_category(cls, value: str) -> str:
        """카테고리 공백을 제거하고 소문자로 정규화한다."""
        return value.strip().lower()
