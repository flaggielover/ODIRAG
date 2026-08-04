from fastapi import APIRouter

from app.api.routes import (
    auth,
    chat,
    crawl_tasks,
    documents,
    evaluations,
    experiments,
    feedback,
    reviews,
    search,
    source_discovery,
    sources,
    system,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(crawl_tasks.router)
api_router.include_router(documents.router)
api_router.include_router(evaluations.router)
api_router.include_router(experiments.router)
api_router.include_router(feedback.router)
api_router.include_router(reviews.router)
api_router.include_router(search.router)
api_router.include_router(sources.router)
api_router.include_router(source_discovery.router)
api_router.include_router(system.router)
