from pydantic import BaseModel, Field, ValidationError

class ToyModel(BaseModel):
    name: str
    cost: int = Field(ge=0, le=100)


valid_model = ToyModel(name="API call", cost=50)
print(valid_model.model_dump())

try:
    ToyModel(name="API call", cost=150)
except ValidationError as exc:
    print("Invalid input:")
    print(exc)