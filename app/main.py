from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import consultation, admin, quiz, hvac_categories
import uvicorn

app = FastAPI(
    title="HVAC Consultation API",
    description="HVAC Consultation System with Token Authentication",
    version="1.0.0",
    swagger_ui_parameters={
        "persistAuthorization": True,
    }
)



# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(consultation.router, prefix="/api/v1", tags=["consultation"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(quiz.router, prefix="/api/v1/quiz", tags=["quiz"])
app.include_router(hvac_categories.router, prefix="/api/v1", tags=["hvac-categories"])






@app.get("/")
async def root():
    return {"message": "Welcome to HVAC Consultation API"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
