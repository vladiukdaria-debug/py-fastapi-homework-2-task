from typing import Any

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import MovieModel, get_db
from database.models import (
    ActorModel,
    CountryModel,
    GenreModel,
    LanguageModel,
)
from schemas.movies import (
    MovieCreateSchema,
    MovieDetailSchema,
    MovieListResponseSchema,
    MovieUpdateSchema,
)


router = APIRouter(prefix="/movies")


async def get_or_create_country(
    db: AsyncSession,
    code: str,
) -> CountryModel:
    stmt = select(CountryModel).where(
        CountryModel.code == code
    )

    result = await db.execute(stmt)
    country = result.scalars().first()

    if country is None:
        country = CountryModel(
            code=code,
            name=None,
        )
        db.add(country)

    return country


async def get_or_create_genre(
    db: AsyncSession,
    name: str,
) -> GenreModel:
    stmt = select(GenreModel).where(
        GenreModel.name == name
    )

    result = await db.execute(stmt)
    genre = result.scalars().first()

    if genre is None:
        genre = GenreModel(name=name)
        db.add(genre)

    return genre


async def get_or_create_actor(
    db: AsyncSession,
    name: str,
) -> ActorModel:
    stmt = select(ActorModel).where(
        ActorModel.name == name
    )

    result = await db.execute(stmt)
    actor = result.scalars().first()

    if actor is None:
        actor = ActorModel(name=name)
        db.add(actor)

    return actor


async def get_or_create_language(
    db: AsyncSession,
    name: str,
) -> LanguageModel:
    stmt = select(LanguageModel).where(
        LanguageModel.name == name
    )

    result = await db.execute(stmt)
    language = result.scalars().first()

    if language is None:
        language = LanguageModel(name=name)
        db.add(language)

    return language


async def get_movie_with_relations(
    db: AsyncSession,
    movie_id: int,
) -> MovieModel | None:
    stmt = (
        select(MovieModel)
        .where(MovieModel.id == movie_id)
        .options(
            selectinload(MovieModel.country),
            selectinload(MovieModel.genres),
            selectinload(MovieModel.actors),
            selectinload(MovieModel.languages),
        )
    )

    result = await db.execute(stmt)

    return result.scalars().first()


@router.get(
    "/",
    response_model=MovieListResponseSchema,
)
async def get_movies(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(
        func.count(MovieModel.id)
    )

    count_result = await db.execute(count_stmt)

    total_items = count_result.scalar_one()

    offset = (page - 1) * per_page

    stmt = (
        select(MovieModel)
        .order_by(MovieModel.id.desc())
        .offset(offset)
        .limit(per_page)
    )

    result = await db.execute(stmt)

    movies = result.scalars().all()

    if not movies:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No movies found.",
        )

    total_pages = (
        total_items + per_page - 1
    ) // per_page

    if page > 1:
        prev_page = (
            f"/theater/movies/"
            f"?page={page - 1}"
            f"&per_page={per_page}"
        )
    else:
        prev_page = None

    if page < total_pages:
        next_page = (
            f"/theater/movies/"
            f"?page={page + 1}"
            f"&per_page={per_page}"
        )
    else:
        next_page = None

    return {
        "movies": movies,
        "prev_page": prev_page,
        "next_page": next_page,
        "total_pages": total_pages,
        "total_items": total_items,
    }


@router.post(
    "/",
    response_model=MovieDetailSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_movie(
    payload: Any = Body(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        movie_data = MovieCreateSchema.model_validate(
            payload
        )
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid input data.",
        )

    stmt = select(MovieModel).where(
        MovieModel.name == movie_data.name,
        MovieModel.date == movie_data.date,
    )

    result = await db.execute(stmt)

    existing_movie = result.scalars().first()

    if existing_movie is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A movie with the name "
                f"'{movie_data.name}' "
                f"and release date "
                f"'{movie_data.date.isoformat()}' "
                f"already exists."
            ),
        )

    country = await get_or_create_country(
        db,
        movie_data.country,
    )

    genres = []

    for genre_name in movie_data.genres:
        genre = await get_or_create_genre(
            db,
            genre_name,
        )
        genres.append(genre)

    actors = []

    for actor_name in movie_data.actors:
        actor = await get_or_create_actor(
            db,
            actor_name,
        )
        actors.append(actor)

    languages = []

    for language_name in movie_data.languages:
        language = await get_or_create_language(
            db,
            language_name,
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
        await db.commit()

    except IntegrityError:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A movie with the name "
                f"'{movie_data.name}' "
                f"and release date "
                f"'{movie_data.date.isoformat()}' "
                f"already exists."
            ),
        )

    created_movie = await get_movie_with_relations(
        db,
        movie.id,
    )

    return created_movie


@router.get(
    "/{movie_id}/",
    response_model=MovieDetailResponseSchema,
)
async def get_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
):
    movie = await get_movie_with_relations(
        db,
        movie_id,
    )

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    return movie


@router.delete(
    "/{movie_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MovieModel).where(
        MovieModel.id == movie_id
    )

    result = await db.execute(stmt)

    movie = result.scalars().first()

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    await db.delete(movie)
    await db.commit()

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


@router.patch("/{movie_id}/")
async def update_movie(
    movie_id: int,
    payload: Any = Body(...),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MovieModel).where(
        MovieModel.id == movie_id
    )

    result = await db.execute(stmt)

    movie = result.scalars().first()

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    try:
        movie_data = MovieUpdateSchema.model_validate(
            payload
        )

    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid input data.",
        )

    update_data = movie_data.model_dump(
        exclude_unset=True
    )

    if any(
        value is None
        for value in update_data.values()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid input data.",
        )

    for field, value in update_data.items():
        setattr(
            movie,
            field,
            value,
        )

    try:
        await db.commit()

    except IntegrityError:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid input data.",
        )

    return {
        "detail": "Movie updated successfully."
    }
