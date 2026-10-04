from fastapi import FastAPI
from pydantic import BaseModel


class Item(BaseModel):
    message: str

app = FastAPI()

@app.post("/hello")
def read_root(item: Item):
    return {"message": item.message}
