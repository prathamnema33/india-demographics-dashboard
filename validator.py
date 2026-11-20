
import re
from datetime import date
from typing import Optional, Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator
)

from passlib.hash import bcrypt


# -----------------------------
# ADDRESS MODEL
# -----------------------------

class Address(BaseModel):
    city: str = Field(min_length=3, max_length=50)
    state: str = Field(min_length=3, max_length=50)
    zip_code: str = Field(pattern=r"^\d{6}$")


# -----------------------------
# USER MODEL
# -----------------------------

class User(BaseModel):

    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8)

    First_name: str = Field(min_length=3, max_length=20)
    Last_name: str = Field(min_length=3, max_length=20)

    literate: str
    dob: date
    age: Optional[int] = None

    address: Address
    religion: str = Field(min_length=3, max_length=20)

    Gender: Literal["Male", "Female"]

    isadult: bool = False
    dod: Optional[date] = None

    # -------------------------
    # PASSWORD VALIDATION
    # -------------------------

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):

        regex = (
            r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)'
            r'(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
        )

        if not re.fullmatch(regex, value):
            raise ValueError(
                "Password must contain uppercase, lowercase, "
                "number and special character"
            )

        return value

    # -------------------------
    # AGE, ADULT STATUS AND DOD VALIDATION
    # -------------------------

    @model_validator(mode="after")
    def calculate_age_and_adult_status(self):

        today = date.today()

        # DOB validation
        if self.dob > today:
            raise ValueError("DOB cannot be in the future")

        # Calculate age automatically
        calculated_age = (
            today.year - self.dob.year
            - (
                (today.month, today.day)
                < (self.dob.month, self.dob.day)
            )
        )

        if calculated_age > 120:
            raise ValueError("Age cannot exceed 120")

        self.age = calculated_age

        # Adult status
        self.isadult = calculated_age >= 18

        # DOD validation
        if self.dod is not None:

            if self.dod < self.dob:
                raise ValueError(
                    "Death date cannot be before DOB"
                )

            if self.dod > today:
                raise ValueError(
                    "Death date cannot be in the future"
                )

        return self


# -----------------------------
# PASSWORD HASHING
# -----------------------------

def hash_password(password: str) -> str:
    return bcrypt.hash(password)
