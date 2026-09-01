from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI

from fastapi.responses import (
    FileResponse,
)

from fastapi.staticfiles import (
    StaticFiles,
)


# =========================================================
# API ROUTERS
# =========================================================

from backend.api.contour_routes import (
    router as contour_router,
)

from backend.api.location_routes import (
    router as location_router,
)

from backend.api.area_routes import (
    router as area_router,
)

from backend.api.place_routes import (
    router as place_router,
)

# =========================================================
# PROJECT DIRECTORIES
# =========================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

FRONTEND_DIR = (
    BASE_DIR
    / "frontend"
)

GENERATED_DIR = (
    BASE_DIR
    / "data"
    / "generated"
)

GENERATED_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

load_dotenv(
    BASE_DIR
    / ".env"
)


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(

    title=(
        "AI-Based Village "
        "Pond Planning System"
    ),

    description=(
        "Terrain, catchment, "
        "land filtering, rainfall "
        "and pond-site planning API."
    ),

    version="0.4.0",
)


# =========================================================
# ROUTERS
# =========================================================

app.include_router(

    contour_router,

    prefix="/api",

    tags=[
        "Contour Analysis"
    ],
)


app.include_router(

    location_router,

    prefix="/api",

    tags=[
        "Automatic Location Analysis"
    ],
)


app.include_router(

    area_router,

    prefix="/api",

    tags=[
        "Drawn Area Analysis"
    ],
)

app.include_router(
    place_router,
    prefix="/api",
    tags=[
        "Map Place Search"
    ],
)

# =========================================================
# STATIC FRONTEND
# =========================================================

app.mount(

    "/static",

    StaticFiles(
        directory=
            str(
                FRONTEND_DIR
            )
    ),

    name="static",
)


# =========================================================
# GENERATED DEM / CONTOUR FILES
# =========================================================

app.mount(

    "/generated",

    StaticFiles(
        directory=
            str(
                GENERATED_DIR
            )
    ),

    name="generated",
)


# =========================================================
# HOME PAGE
# =========================================================

@app.get(
    "/",
    include_in_schema=False,
)
def root():

    return FileResponse(
        FRONTEND_DIR
        / "index.html"
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():

    return {
        "status": "healthy"
    }
