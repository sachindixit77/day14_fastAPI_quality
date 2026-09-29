import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from database import engine, get_db
from db_models import Employee
from models import (
    EmployeeCreate,
    EmployeeResponse,
    EmployeeListResponse
)


# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# APPLICATION LIFESPAN
# ---------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Employee API started")

    yield

    logger.info("Employee API stopped")


# ---------------------------------------------------------
# FASTAPI APPLICATION
# ---------------------------------------------------------

app = FastAPI(
    title="Employee Management API - Day 14",
    description=(
        "Employee Management API with pagination, search, "
        "sorting, filtering, validation, error handling "
        "and logging."
    ),
    version="2.0.0",
    lifespan=lifespan
)


# ---------------------------------------------------------
# COMMON ERROR RESPONSE
# ---------------------------------------------------------

def error_response(
    status_code: int,
    message: str,
    error_type: str
):
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "type": error_type,
                "message": message
            }
        }
    )


# ---------------------------------------------------------
# VALIDATION ERROR HANDLER
# ---------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    logger.warning(
        "Validation error: %s",
        exc.errors()
    )

    return error_response(
        status_code=422,
        message="Invalid request data",
        error_type="VALIDATION_ERROR"
    )


# ---------------------------------------------------------
# GENERAL EXCEPTION HANDLER
# ---------------------------------------------------------

@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception
):
    logger.error(
        "Unexpected server error: %s",
        exc
    )

    return error_response(
        status_code=500,
        message="Internal server error",
        error_type="INTERNAL_SERVER_ERROR"
    )


# ---------------------------------------------------------
# CREATE EMPLOYEE
# ---------------------------------------------------------

@app.post(
    "/employees",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED
)
def create_employee(
    employee: EmployeeCreate,
    db: Session = Depends(get_db)
):
    new_employee = Employee(
        name=employee.name,
        email=str(employee.email),
        department=employee.department,
        designation=employee.designation,
        salary=employee.salary
    )

    try:
        db.add(new_employee)
        db.commit()
        db.refresh(new_employee)

        logger.info(
            "Employee created successfully: id=%s",
            new_employee.id
        )

        return new_employee

    except IntegrityError:
        db.rollback()

        logger.warning(
            "Duplicate employee email: %s",
            employee.email
        )

        return error_response(
            status_code=409,
            message="Employee with this email already exists",
            error_type="DUPLICATE_EMPLOYEE"
        )

    except SQLAlchemyError as exc:
        db.rollback()

        logger.error(
            "Database error while creating employee: %s",
            exc
        )

        return error_response(
            status_code=500,
            message="Database error while creating employee",
            error_type="DATABASE_ERROR"
        )


# ---------------------------------------------------------
# GET EMPLOYEES
# PAGINATION + SEARCH + FILTER + SORT
# ---------------------------------------------------------

@app.get(
    "/employees",
    response_model=EmployeeListResponse
)
def get_employees(
    request: Request,

    page: int = Query(
        default=1,
        ge=1,
        description="Page number"
    ),

    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of employees per page"
    ),

    search: str | None = Query(
        default=None,
        description=(
            "Search by name, email, department "
            "or designation"
        )
    ),

    department: str | None = Query(
        default=None,
        description="Filter by department"
    ),

    sort: str = Query(
        default="id",
        description=(
            "Sort by id, name, email, department "
            "or salary"
        )
    ),

    db: Session = Depends(get_db)
):
    logger.info(
        "Employee list request: page=%s limit=%s "
        "search=%s department=%s sort=%s",
        page,
        limit,
        search,
        department,
        sort
    )

    # -----------------------------------------------------
    # ALLOWED SORT FIELDS
    # -----------------------------------------------------

    allowed_sort_fields = {
        "id": Employee.id,
        "name": Employee.name,
        "email": Employee.email,
        "department": Employee.department,
        "salary": Employee.salary
    }

    if sort not in allowed_sort_fields:
        return error_response(
            status_code=400,
            message=(
                "Invalid sort field. Allowed values: "
                "id, name, email, department, salary"
            ),
            error_type="INVALID_SORT_FIELD"
        )

    # -----------------------------------------------------
    # BASE QUERY
    # -----------------------------------------------------

    statement = select(Employee)

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    if search:
        search_pattern = f"%{search}%"

        statement = statement.where(
            or_(
                Employee.name.ilike(search_pattern),
                Employee.email.ilike(search_pattern),
                Employee.department.ilike(search_pattern),
                Employee.designation.ilike(search_pattern)
            )
        )

    # -----------------------------------------------------
    # DEPARTMENT FILTER
    # -----------------------------------------------------

    if department:
        statement = statement.where(
            Employee.department.ilike(department)
        )

    # -----------------------------------------------------
    # TOTAL RECORDS
    # -----------------------------------------------------

    count_statement = select(
        func.count()
    ).select_from(
        statement.subquery()
    )

    total_records = db.scalar(count_statement) or 0

    # -----------------------------------------------------
    # TOTAL PAGES
    # -----------------------------------------------------

    total_pages = (
        (total_records + limit - 1) // limit
        if total_records > 0
        else 0
    )

    # -----------------------------------------------------
    # PAGE VALIDATION
    # -----------------------------------------------------

    if total_pages > 0 and page > total_pages:
        return error_response(
            status_code=404,
            message=(
                f"Page {page} does not exist. "
                f"Available pages: 1 to {total_pages}"
            ),
            error_type="PAGE_NOT_FOUND"
        )

    # -----------------------------------------------------
    # OFFSET
    # -----------------------------------------------------

    offset = (page - 1) * limit

    # -----------------------------------------------------
    # SORTING
    # -----------------------------------------------------

    statement = statement.order_by(
        allowed_sort_fields[sort]
    )

    # -----------------------------------------------------
    # PAGINATION
    # -----------------------------------------------------

    statement = (
        statement
        .offset(offset)
        .limit(limit)
    )

    employees = db.scalars(statement).all()

    # -----------------------------------------------------
    # NEXT PAGE URL
    # -----------------------------------------------------

    next_page = None

    if page < total_pages:
        next_page = str(
            request.url.include_query_params(
                page=page + 1
            )
        )

    # -----------------------------------------------------
    # PREVIOUS PAGE URL
    # -----------------------------------------------------

    previous_page = None

    if page > 1:
        previous_page = str(
            request.url.include_query_params(
                page=page - 1
            )
        )

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    return {
        "data": employees,

        "pagination": {
            "current_page": page,
            "limit": limit,
            "total_records": total_records,
            "total_pages": total_pages,
            "next_page": next_page,
            "previous_page": previous_page
        }
    }


# ---------------------------------------------------------
# GET SINGLE EMPLOYEE
# ---------------------------------------------------------

@app.get(
    "/employees/{id}",
    response_model=EmployeeResponse
)
def get_employee(
    id: int,
    db: Session = Depends(get_db)
):
    logger.info(
        "Get employee request: id=%s",
        id
    )

    employee = db.get(Employee, id)

    if employee is None:
        logger.warning(
            "Employee not found: id=%s",
            id
        )

        return error_response(
            status_code=404,
            message="Employee not found",
            error_type="EMPLOYEE_NOT_FOUND"
        )

    return employee


# ---------------------------------------------------------
# UPDATE EMPLOYEE
# ---------------------------------------------------------

@app.put(
    "/employees/{id}",
    response_model=EmployeeResponse
)
def update_employee(
    id: int,
    employee_data: EmployeeCreate,
    db: Session = Depends(get_db)
):
    logger.info(
        "Update employee request: id=%s",
        id
    )

    employee = db.get(Employee, id)

    if employee is None:
        logger.warning(
            "Employee not found for update: id=%s",
            id
        )

        return error_response(
            status_code=404,
            message="Employee not found",
            error_type="EMPLOYEE_NOT_FOUND"
        )

    employee.name = employee_data.name
    employee.email = str(employee_data.email)
    employee.department = employee_data.department
    employee.designation = employee_data.designation
    employee.salary = employee_data.salary

    try:
        db.commit()
        db.refresh(employee)

        logger.info(
            "Employee updated successfully: id=%s",
            id
        )

        return employee

    except IntegrityError:
        db.rollback()

        logger.warning(
            "Duplicate email during update: %s",
            employee_data.email
        )

        return error_response(
            status_code=409,
            message="Employee with this email already exists",
            error_type="DUPLICATE_EMPLOYEE"
        )

    except SQLAlchemyError as exc:
        db.rollback()

        logger.error(
            "Database error while updating employee: %s",
            exc
        )

        return error_response(
            status_code=500,
            message="Database error while updating employee",
            error_type="DATABASE_ERROR"
        )


# ---------------------------------------------------------
# DELETE EMPLOYEE
# ---------------------------------------------------------

@app.delete("/employees/{id}")
def delete_employee(
    id: int,
    db: Session = Depends(get_db)
):
    logger.info(
        "Delete employee request: id=%s",
        id
    )

    employee = db.get(Employee, id)

    if employee is None:
        logger.warning(
            "Employee not found for deletion: id=%s",
            id
        )

        return error_response(
            status_code=404,
            message="Employee not found",
            error_type="EMPLOYEE_NOT_FOUND"
        )

    try:
        db.delete(employee)
        db.commit()

        logger.info(
            "Employee deleted successfully: id=%s",
            id
        )

        return {
            "success": True,
            "message": "Employee deleted successfully"
        }

    except SQLAlchemyError as exc:
        db.rollback()

        logger.error(
            "Database error while deleting employee: %s",
            exc
        )

        return error_response(
            status_code=500,
            message="Database error while deleting employee",
            error_type="DATABASE_ERROR"
        )


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------

@app.get("/health")
def health_check():

    try:

        with engine.connect() as connection:
            connection.execute(select(1))

        return {
            "success": True,
            "status": "healthy",
            "database": "connected"
        }

    except SQLAlchemyError as exc:

        logger.error(
            "Database health check failed: %s",
            exc
        )

        return error_response(
            status_code=500,
            message="Database connection failed",
            error_type="DATABASE_ERROR"
        )