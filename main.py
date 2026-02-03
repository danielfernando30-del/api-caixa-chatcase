from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

TOKEN = "SEU_TOKEN_SECRETO_AQUI"

class RequestBody(BaseModel):
    loteria: str

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/caixa/resultados")
def resultados(
    body: RequestBody,
    authorization: str | None = Header(default=None)
):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    if body.loteria != "lotofacil":
        raise HTTPException(status_code=400, detail="Loteria inválida")

    return {
            sorteio = [
        "01","02","03","04","05",
        "06","08","09","15","18",
        "19","20","22","23","24"
    ]

    return {
        "dataApuracao": "03/02/2026",
        "concurso": "3602",
        "sorteioTexto": " ".join([f"[{n}]" for n in sorteio]),
        "proxNumero": "3603",
        "proxData": "05/02/2026",
        "proxValorEstimado": "5000000.00"
    }

            }
        }
    }
