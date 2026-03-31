from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from healthsync.api.routes.auth import router as auth_router
from healthsync.api.routes.health import router as health_router
from healthsync.api.routes.patients import router as patients_router
from healthsync.api.routes.glucose_readings import router as glucose_readings_router
from healthsync.api.routes.health import router as db_health_router
from healthsync.api.routes.visits import router as visits_router
from healthsync.api.routes.clinicians import router as clinicians_router
from healthsync.api.routes.allergies import router as allergies_router
from healthsync.api.routes.access_permissions import router as access_permissions_router
from healthsync.api.routes.preferences import router as preferences_router
from healthsync.api.routes.medications import router as medications_router
from healthsync.api.routes.prescriptions import router as prescriptions_router
from healthsync.api.routes.lifestyle import router as lifestyle_router

from healthsync.db.connection import close_all_connections

app = FastAPI(title="HealthSYNC API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://healthsyncfrontend-production.up.railway.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Routers
# ---------------------------
app.include_router(health_router)
app.include_router(db_health_router)
app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(visits_router)
app.include_router(access_permissions_router)
app.include_router(clinicians_router)
app.include_router(allergies_router)
app.include_router(glucose_readings_router)
app.include_router(preferences_router)
app.include_router(medications_router)
app.include_router(prescriptions_router)
app.include_router(lifestyle_router)
app.include_router(medications_router)
app.include_router(prescriptions_router)


# ---------------------------
# Graceful shutdown
# ---------------------------
@app.on_event("shutdown")
def shutdown_event():
    close_all_connections()
