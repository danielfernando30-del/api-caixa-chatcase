from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import httpx

app = FastAPI()

# ✅ No Render, configure a variável de ambiente TOKEN
TOKEN = os.getenv("TOKEN", "SEU_TOKEN_SECRETO_AQUI")

BASE_URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api"


class RequestBody(BaseModel):
    loteria: str


@app.get("/")
def health():
    return {"status": "ok"}


def format_brl(value) -> str:
    """Formata número para pt-BR simples (1.800.000,00)."""
    try:
        v = float(value)
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


@app.post("/caixa/resultados")
async def resultados(
    body: RequestBody,
    authorization: str | None = Header(default=None),
):
    # --- Auth ---
    if not authorization or authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    loteria = (body.loteria or "").strip().lower()
    if loteria != "lotofacil":
        raise HTTPException(status_code=400, detail="Loteria inválida")

    # --- Busca oficial CAIXA (Lotofácil) ---
    url = f"{BASE_URL}/lotofacil"
    headers = {
        "Accept": "application/json",
        "User-Agent": "api-caixa-chatcase/1.0",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            j = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar CAIXA: {e}")

    # Campos que a API oficial costuma retornar:
    concurso = j.get("numero")
    data_apuracao = j.get("dataApuracao")
    dezenas = j.get("listaDezenas") or []
    prox_numero = j.get("numeroConcursoProximo")
    prox_data = j.get("dataProximoConcurso")
    prox_valor = j.get("valorEstimadoProximoConcurso")
    acumulado = j.get("acumulado")

    sorteio_texto = " ".join([f"[{d}]" for d in dezenas])
    prox_valor_fmt = format_brl(prox_valor)

    # ✅ Mensagem pronta para WhatsApp (Chatcase só repassa)
    mensagem = (
        f"📌 *Anote o resultado da Lotofácil*\n\n"
        f"📅 Data: {data_apuracao}\n"
        f"🔢 Concurso: {concurso}\n\n"
        f"🎯 Números sorteados:\n{sorteio_texto}\n\n"
        f"➡️ *Próximo concurso*\n"
        f"📆 Data: {prox_data}\n"
        f"🔢 Concurso: {prox_numero}\n"
        f"💰 Estimativa: R$ {prox_valor_fmt}\n"
        f"{'✅ Acumulou!' if acumulado else 'ℹ️ Não acumulou.'}"
    )

    # Retorna mensagem + dados estruturados (útil para debug/mapeamento)
    return JSONResponse(
        {
            "mensagem": mensagem,
            "data": {
                "dataApuracao": data_apuracao,
                "concurso": str(concurso) if concurso is not None else "",
                "sorteio": dezenas,
                "sorteioTexto": sorteio_texto,
                "acumulado": bool(acumulado),
                "proximoConcurso": {
                    "numero": str(prox_numero) if prox_numero is not None else "",
                    "data": prox_data or "",
                    "valorEstimado": prox_valor_fmt,
                },
            },
        }
    )

