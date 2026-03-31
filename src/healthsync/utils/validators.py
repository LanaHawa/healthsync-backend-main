from typing import Set
from fastapi import HTTPException


ALLOWED_UNITS: Set[str] = {"mg/dL", "mmol/L"}
ALLOWED_DEVICE_TYPES: Set[str] = {"Libre", "Dexcom"}

MIN_GLUCOSE_VALUE = 20.0
MAX_GLUCOSE_VALUE = 600.0



def validate_unit(unit: str) -> str:
    """
    Validate that the unit is either 'mg/dL' or 'mmol/L'.

    Args:
        unit (str): The unit to validate.

    Raises:
        HTTPException: If the unit is not valid.

    Returns:
        The validated unit string.

    """
    u = (unit or "").strip()
    if u not in ALLOWED_UNITS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid unit '{unit}'. Allowed units are: {', '.join(ALLOWED_UNITS)}.",
        )

    return u

def validate_device_type(device_type: str) -> str:
    """
    Validate that the device type is either 'Libre' or 'Dexcom'.

    Args:
        device_type (str): The device type to validate.

    Raises:
        HTTPException: If the device type is not valid.

    Returns:
        The validated device type string.
    """
    dt = (device_type or "").strip()
    if dt not in ALLOWED_DEVICE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid device type '{device_type}'. Allowed types are: {', '.join(ALLOWED_DEVICE_TYPES)}.",
        )
    return dt

def validate_glucose_value(value: float) -> float:
    """
    Validate that the glucose value is within a reasonable range.

    Args:
        value (float): The glucose value to validate.

    Raises:
        HTTPException: If the glucose value is out of range.

    Returns:
        The validated glucose value.
    """
    if value < MIN_GLUCOSE_VALUE or value > MAX_GLUCOSE_VALUE:
        raise HTTPException(
            status_code=400,
            detail=f"Glucose value {value} is out of range. Must be between {MIN_GLUCOSE_VALUE} and {MAX_GLUCOSE_VALUE}.",
        )
    return value