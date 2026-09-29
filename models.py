from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


ALLOWED_DEPARTMENTS = {
    "IT",
    "HR",
    "Finance",
    "Marketing",
    "Sales"
}


class EmployeeCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=100
    )

    email: EmailStr

    department: str = Field(
        min_length=2,
        max_length=50
    )

    designation: str = Field(
        min_length=2,
        max_length=100
    )

    salary: float = Field(
        gt=0
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Employee name is required")

        return value

    @field_validator("department")
    @classmethod
    def validate_department(cls, value: str) -> str:
        value = value.strip()

        if value not in ALLOWED_DEPARTMENTS:
            allowed = ", ".join(sorted(ALLOWED_DEPARTMENTS))

            raise ValueError(
                f"Invalid department. Allowed departments: {allowed}"
            )

        return value


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    department: str
    designation: str
    salary: float


class PaginationInfo(BaseModel):
    current_page: int
    limit: int
    total_records: int
    total_pages: int

    next_page: str | None
    previous_page: str | None


class EmployeeListResponse(BaseModel):
    data: list[EmployeeResponse]
    pagination: PaginationInfo