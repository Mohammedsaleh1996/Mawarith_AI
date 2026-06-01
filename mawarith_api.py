# -*- coding: utf-8 -*-
from fastapi import FastAPI
from pydantic import BaseModel
from mawarith_ai_runtime import answer

app = FastAPI(title="Mawareth AI Runtime Final v8")

class AskRequest(BaseModel):
    question: str

@app.post("/ask")
def ask(req: AskRequest):
    return {"answer": answer(req.question)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
