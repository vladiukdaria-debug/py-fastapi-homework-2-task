import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from database.models import MovieStatusEnum


class CountryResponseSchema(BaseModel):
    id: int
    code: str
    name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class GenreResponseSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ActorResponseSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class LanguageResponseSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class MovieListItemSchema(BaseModel):
    id: int
    name: str
    date: datetime.date
    score: float
    overview: str

    model_config = ConfigDict(from_attributes=True)


class MovieListResponseSchema(BaseModel):
    movies: list[MovieListItemSchema]
    prev_page: str | None = None
    next_page: str | None = None
    total_pages: int
    total_items: int


class MovieDetailResponseSchema(BaseModel):
    id: int
    name: str
    date: datetime.date
    score: float
    overview: str
    status: MovieStatusEnum
    budget: float
    revenue: float
    country: CountryResponseSchema
    genres: list[GenreResponseSchema]
    actors: list[ActorResponseSchema]
    languages: list[LanguageResponseSchema]

    model_config = ConfigDict(from_attributes=True)


class MovieCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    date: datetime.date
    score: float = Field(ge=0, le=100)
    overview: str = Field(min_length=1)
    status: MovieStatusEnum
    budget: float = Field(ge=0)
    revenue: float = Field(ge=0)
    country: str = Field(min_length=2, max_length=3)
    genres: list[str]
    actors: list[str]
    languages: list[str]

    @field_validator("date")
    @classmethod
    def validate_date(
        cls,
        value: datetime.date,
    ) -> datetime.date:
        maximum_date = (
            datetime.date.today()
            + datetime.timedelta(days=365)
        )

        if value > maximum_date:
            raise ValueError(
                "Release date cannot be more than one year in the future."
            )

        return value

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("genres", "actors", "languages")
    @classmethod
    def validate_names(cls, values: list[str]) -> list[str]:
        cleaned_values: list[str] = []

        for value in values:
            cleaned_value = value.strip()

            if not cleaned_value:
                raise ValueError("Names must not be empty.")

            if cleaned_value not in cleaned_values:
                cleaned_values.append(cleaned_value)

        return cleaned_values


class MovieUpdateSchema(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    date: datetime.date | None = None
    score: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    overview: str | None = Field(
        default=None,
        min_length=1,
    )
    status: MovieStatusEnum | None = None
    budget: float | None = Field(
        default=None,
        ge=0,
    )
    revenue: float | None = Field(
        default=None,
        ge=0,
    )

    @field_validator("date")
    @classmethod
    def validate_date(
        cls,
        value: datetime.date | None,
    ) -> datetime.date | None:
        if value is None:
            return None

        maximum_date = (
            datetime.date.today()
            + datetime.timedelta(days=365)
        )

        if value > maximum_date:
            raise ValueError(
                "Release date cannot be more than one year in the future."
            )

        return value


