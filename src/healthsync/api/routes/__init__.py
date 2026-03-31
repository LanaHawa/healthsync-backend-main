from fastapi import APIRouter

all_routers: list[APIRouter] = []

# Import routers one-by-one so a missing file doesn't break everything
try:
    from .health import router as health_router
    all_routers.append(health_router)
except Exception as e:
    print("Failed to import health router:", e)

try:
    from .patients import router as patients_router
    all_routers.append(patients_router)
except Exception as e:
    print("Failed to import patients router:", e)

try:
    from .devices import router as devices_router
    all_routers.append(devices_router)
except Exception as e:
    print("Failed to import devices router:", e)

try:
    from .glucose_readings import router as glucose_router
    all_routers.append(glucose_router)
except Exception as e:
    print("Failed to import glucose_readings router:", e)
