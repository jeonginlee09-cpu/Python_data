"""Pydantic v2로 API 응답 데이터를 검증하고 정상/오염 레코드를 분류한다."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
)


DATA_PATH = Path(__file__).resolve().parent.parent / "api_response.json"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Seller(BaseModel):
    """상품에 포함된 중첩 판매자 정보."""

    country: str
    tier: str
    score: Annotated[float, Field(ge=0, le=100)]


class Product(BaseModel):
    """API에서 받아야 하는 정상 상품 데이터의 스키마."""

    id: StrictInt
    username: str
    email: str
    age: Annotated[StrictInt, Field(ge=0, le=120)]
    is_active: StrictBool
    signup_date: date
    profile: Seller
    tags: list[str] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """이메일의 기본 형식을 검사한다."""
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("올바른 이메일 형식이 아닙니다")
        return value


def load_data(path: Path = DATA_PATH) -> list[dict[str, Any]]:
    """API 응답 JSON에서 results 배열을 읽는다."""
    with path.open(encoding="utf-8") as file:
        response = json.load(file)

    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        raise ValueError("api_response.json에 results 배열이 필요합니다")
    return response["results"]


def validate_products(
    data: list[dict[str, Any]],
) -> tuple[list[Product], list[dict[str, Any]]]:
    """모든 레코드를 검증하되 실패해도 중단하지 않고 오류를 기록한다."""
    valid: list[Product] = []
    invalid: list[dict[str, Any]] = []

    for index, row in enumerate(data):
        try:
            valid.append(Product.model_validate(row))
        except ValidationError as error:
            invalid.append(
                {
                    "index": index,
                    "data": row,
                    "errors": error.errors(include_url=False),
                }
            )

    return valid, invalid


def format_location(location: tuple[int | str, ...]) -> str:
    """중첩 필드 위치를 seller.region 형태로 표시한다."""
    return ".".join(str(part) for part in location)


def print_report(
    total: int,
    valid: list[Product],
    invalid: list[dict[str, Any]],
) -> None:
    """검증 요약과 오염 레코드별 실패 이유를 출력한다."""
    print(f"전체 {total}건 / 유효 {len(valid)}건 / 오염 {len(invalid)}건")

    if invalid:
        print("\n-- 오염 데이터 상세 --")

    for item in invalid:
        for error in item["errors"]:
            field = format_location(error["loc"])
            print(f"{item['index']:<4}{field:<20}{error['msg']}")


def main() -> None:
    data = load_data()
    valid, invalid = validate_products(data)
    print_report(len(data), valid, invalid)


if __name__ == "__main__":
    main()
