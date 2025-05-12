# from fastapi import FastAPI
# import uvicorn

# app = FastAPI(
#     title="VOICERA", 
#     description="A VOICERA APP",
#     version="1.0.0"
# )

# @app.get("/health")
# async def health_check():
#     return {"status": "ok"}

# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8000)

from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok"}


# uvicorn Backend.api.health:app --reload
