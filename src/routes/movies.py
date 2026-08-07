from typing import Any, cast

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
)
from starlette.responses import Response
from pydantic import ValidationError
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from starlette import status

from database.models import (
    ActorModel,
    CountryModel,
    GenreModel,
    LanguageModel,
    MovieModel,
)
from database.session_postgresql import get_postgresql_db
from schemas.movies import (
    MovieCreateSchema,
    MovieDetailResponseSchema,
    MovieListResponseSchema,
    MovieUpdateSchema,
)


router = APIRouter(
    prefix="/movies",
    tags=["movies"],
)


async def get_or_create_by_name(
    db: AsyncSession,
    model: Any,
    name: str,
) -> Any:
    query = select(model).where(model.name == name)
    result = await db.execute(query)
    item = result.scalar_one_or_none()

    if item is None:
        item = model(name=name)
        db.add(item)
        await db.flush()

    return item


async def get_movie_with_relations(
    db: AsyncSession,
    movie_id: int,
) -> MovieModel | None:
    query = (
        select(MovieModel)
        .where(MovieModel.id == movie_id)
        .options(
            joinedload(MovieModel.country),
            selectinload(MovieModel.genres),
            selectinload(MovieModel.actors),
            selectinload(MovieModel.languages),
        )
    )

    result = await db.execute(query)
    return result.scalar_one_or_none()


@router.get(
    "/",
    response_model=MovieListResponseSchema,
)
async def get_movies(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=20),
    db: AsyncSession = Depends(get_postgresql_db),
) -> MovieListResponseSchema:
    count_query = select(func.count(MovieModel.id))
    count_result = await db.execute(count_query)
    total_items = count_result.scalar_one()

    offset = (page - 1) * per_page

    movies_query = (
        select(MovieModel)
        .order_by(desc(MovieModel.id))
        .offset(offset)
        .limit(per_page)
    )

    movies_result = await db.execute(movies_query)
    movies = movies_result.scalars().all()

    if not movies:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No movies found.",
        )

    total_pages = (
        total_items + per_page - 1
    ) // per_page

    prev_page = None
    next_page = None

    if page > 1:
        prev_page = (
            f"/theater/movies/"
            f"?page={page - 1}&per_page={per_page}"
        )

    if page < total_pages:
        next_page = (
            f"/theater/movies/"
            f"?page={page + 1}&per_page={per_page}"
        )

    return MovieListResponseSchema(
        movies=movies,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )


@router.post(
    "/",
    response_model=MovieDetailResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_movie(
    raw_data: Any = Body(...),
    db: AsyncSession = Depends(get_postgresql_db),
) -> MovieModel:
    try:
        movie_data = MovieCreateSchema.model_validate(raw_data)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid input data.",
        ) from error

    duplicate_query = select(MovieModel).where(
        MovieModel.name == movie_data.name,
        MovieModel.date == movie_data.date,
    )

    duplicate_result = await db.execute(duplicate_query)
    existing_movie = duplicate_result.scalar_one_or_none()

    if existing_movie is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A movie with the same name and release date "
                "already exists."
            ),
        )

    country_query = select(CountryModel).where(
        CountryModel.code == movie_data.country
    )

    country_result = await db.execute(country_query)
    country = country_result.scalar_one_or_none()

    if country is None:
        country = CountryModel(
            code=movie_data.country,
        )
        db.add(country)
        await db.flush()

    genres = []

    for genre_name in movie_data.genres:
        genre = await get_or_create_by_name(
            db=db,
            model=GenreModel,
            name=genre_name,
        )
        genres.append(genre)

    actors = []

    for actor_name in movie_data.actors:
        actor = await get_or_create_by_name(
            db=db,
            model=ActorModel,
            name=actor_name,
        )
        actors.append(actor)

    languages = []

    for language_name in movie_data.languages:
        language = await get_or_create_by_name(
            db=db,
            model=LanguageModel,
            name=language_name,
        )
        languages.append(language)

    movie = MovieModel(
        name=movie_data.name,
        date=movie_data.date,
        score=movie_data.score,
        overview=movie_data.overview,
        status=movie_data.status,
        budget=movie_data.budget,
        revenue=movie_data.revenue,
        country=country,
        genres=genres,
        actors=actors,
        languages=languages,
    )

    db.add(movie)
    try:
        await db.flush()

        movie_id = cast(int, movie.id)

        await db.commit()

    except IntegrityError as error:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A movie with the same name and release date "
                "already exists."
            )
        ) from error

    created_movie = await get_movie_with_relations(
        db=db,
        movie_id=movie_id,
    )

    if created_movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    return created_movie


@router.get(
    "/{movie_id}/",
    response_model=MovieDetailResponseSchema,
)
async def get_movie_by_id(
    movie_id: int,
    db: AsyncSession = Depends(get_postgresql_db),
) -> MovieModel:
    movie = await get_movie_with_relations(
        db=db,
        movie_id=movie_id,
    )

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    return movie


@router.patch(
    "/{movie_id}/",
    response_model=MovieDetailResponseSchema,
)
async def update_movie(
    movie_id: int,
    raw_data: Any = Body(...),
    db: AsyncSession = Depends(get_postgresql_db),
) -> MovieModel:
    movie = await get_movie_with_relations(
        db=db,
        movie_id=movie_id,
    )

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    try:
        movie_data = MovieUpdateSchema.model_validate(raw_data)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid input data.",
        ) from error

    update_data = movie_data.model_dump(
        exclude_unset=True,
    )

    for field_name, field_value in update_data.items():
        setattr(movie, field_name, field_value)

    try:
        await db.commit()

    except IntegrityError as error:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A movie with the same name and release date "
                "already exists."
            ),
        ) from error

    updated_movie = await get_movie_with_relations(
        db=db,
        movie_id=movie_id,
    )

    if updated_movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    return updated_movie


@router.delete(
    "/{movie_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_postgresql_db),
) -> Response:
    query = select(MovieModel).where(
        MovieModel.id == movie_id
    )

    result = await db.execute(query)
    movie = result.scalar_one_or_none()

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    await db.delete(movie)
    await db.commit()

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
