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
    "mensagem": (
        f"📌 *Anote o resultado da Lotofácil*\n\n"
        f"📅 Data: {data_apuracao}\n"
        f"🔢 Concurso: {concurso}\n\n"
        f"🎯 Números sorteados:\n{sorteio_texto}\n\n"
        f"➡️ *Próximo concurso*\n"
        f"📆 Data: {prox_data}\n"
        f"💰 Estimativa: R$ {prox_valor}"
    )
}
