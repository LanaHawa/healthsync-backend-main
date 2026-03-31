# backend/src/healthsync/data/schemas/common.py

from pydantic import BaseModel


class Message(BaseModel):
    """
    Generic success message response.
    Example:
        {"message": "Operation successful"}
    """
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Operation successful"
            }
        }
