from pydantic import BaseModel

class LocationResponse(BaseModel):
    name: str
    title: str
    syncEnabled: bool

class LocationToggleRequest(BaseModel):
    locationName: str
    title: str
    syncEnabled: bool
