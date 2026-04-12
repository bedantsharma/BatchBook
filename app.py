from fastapi import FastAPI
from routes.student_route import router as student_router
from fastapi import FastAPI

app = FastAPI(
    title="Batch Book",
    description="Clean, well-documented API for batch book application 🚀",
    version="1.0.0",
    contact={
        "name": "Bedant Sharma",
        "email": "bedant.sharma.dev@gmail.com",
    },
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(router=student_router)