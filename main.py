from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import time

app = FastAPI()

# Token que o Chatcase usa (Render -> ENV TOKEN)
TOKEN = os.getenv("TOKEN", "SEU_TOKEN_SECRETO_AQUI")

# Token apenas para atualizar cache (Render -> ENV ADMIN_TOKEN)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "SEU_ADMIN_TOKEN_AQUI")

# Cache em memória
CACHE: dict[str, dict] = {}
CACHE_META: dict[str, dict] = {}

SUPPORTED = {"lotofacil", "megasena", "quina"}


class ReqResultados(BaseModel):
    loteria: str


class ReqAtualizar(BaseModel):
    loteria: str
    data: dict  # payload completo já pronto


def build_message(loteria: str, data: dict) -> str:
    titulo = {"lotofacil": "Lotofácil", "megasena": "Mega-Sena", "quina": "Quina"}.get(loteria, loteria)

    data_apuracao = data.get("dataApuracao", "")
    concurso = data.get("concurso", "")
    sorteio_texto = data.get("sorteioTexto", "")
    acumulado = bool(data.get("acumulado", False))

    prox = data.get("proximoConcurso", {}) or {}
    prox_numero = prox.get("numero", "")
    prox_data = prox.get("data", "")
    prox_valor = prox.get("valorEstimado", "")

    acumulado_txt = "✅ *Acumulou!*" if acumulado else "ℹ️ *Não acumulou.*"

    return (
        f"📌 *Anote o resultado da {titulo}*\n\n"
        f"📅 Data: {data_apuracao}\n"
        f"🔢 Concurso: {concurso}\n\n"
        f"🎯 Números sorteados:\n{sorteio_texto}\n\n"
        f"➡️ *Próximo concurso*\n"
        f"📆 Data: {prox_data}\n"
        f"🔢 Concurso: {prox_numero}\n"
        f"💰 Estimativa: R$ {prox_valor}\n"
        f"{acumulado_txt}"
    )


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/caixa/atualizar")
def atualizar_cache(
    payload: ReqAtualizar,
    authorization: str | None = Header(default=None),
):
    """
    Endpoint para um 'worker' externo (seu PC/VPS) enviar os resultados.
    Use: Authorization: Bearer <ADMIN_TOKEN>
    """
    if not authorization or authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    loteria = (payload.loteria or "").strip().lower()
    if loteria not in SUPPORTED:
        raise HTTPException(status_code=400, detail="Loteria inválida")

    data = payload.data or {}
    # garante mensagem pronta
    data["mensagem"] = build_message(loteria, data)

    CACHE[loteria] = data
    CACHE_META[loteria] = {"updated_at": int(time.time())}

    return {"status": "ok", "loteria": loteria, "updated_at": CACHE_META[loteria]["updated_at"]}


@app.post("/caixa/resultados")
def resultados(
    body: ReqResultados,
    authorization: str | None = Header(default=None),
):
    """
    Endpoint que o Chatcase chama.
    Use: Authorization: Bearer <TOKEN>
    Body: {"loteria":"lotofacil"}
    """
    if not authorization or authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    loteria = (body.loteria or "").strip().lower()
    if loteria not in SUPPORTED:
        raise HTTPException(status_code=400, detail="Loteria inválida")

    data = CACHE.get(loteria)
    meta = CACHE_META.get(loteria, {})

    if not data:
        return JSONResponse(
            status_code=200,
            content={
                "data": {
                    "mensagem": "⚠️ Ainda não tenho um resultado salvo para essa loteria. Tente novamente em instantes.",
                    "status_cache": "empty",
                },
                "meta": meta,
            },
        )

    return JSONResponse(
        status_code=200,
        content={"data": data, "meta": meta},
    )
