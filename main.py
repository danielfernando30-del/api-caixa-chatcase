from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import time
import httpx

app = FastAPI()

# No Render: Environment -> add KEY=TOKEN VALUE=seu_token
TOKEN = os.getenv("TOKEN", "SEU_TOKEN_SECRETO_AQUI")

BASE_URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api"

# Cache simples em memória: { "lotofacil": {"ts":..., "payload": {...}} }
CACHE: dict[str, dict] = {}
CACHE_TTL_SECONDS = 120  # 2 min (ajuste como quiser)


class RequestBody(BaseModel):
    loteria: str


@app.get("/")
def health():
    return {"status": "ok"}


def format_brl(value) -> str:
    """Formata número para pt-BR simples: 1800000 -> 1.800.000,00"""
    try:
        v = float(value)
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


def build_message(data: dict) -> str:
    """Monta mensagem pronta para WhatsApp."""
    lot = (data.get("loteria") or "").lower()
    titulo = "Lotofácil" if lot == "lotofacil" else lot.title()

    acumulado = data.get("acumulado", False)
    acumulado_txt = "✅ *Acumulou!*" if acumulado else "ℹ️ *Não acumulou.*"

    msg = (
        f"📌 *Anote o resultado da {titulo}*\n\n"
        f"📅 Data: {data.get('dataApuracao','')}\n"
        f"🔢 Concurso: {data.get('concurso','')}\n\n"
        f"🎯 Números sorteados:\n{data.get('sorteioTexto','')}\n\n"
        f"➡️ *Próximo concurso*\n"
        f"📆 Data: {data.get('proximoConcurso',{}).get('data','')}\n"
        f"🔢 Concurso: {data.get('proximoConcurso',{}).get('numero','')}\n"
        f"💰 Estimativa: R$ {data.get('proximoConcurso',{}).get('valorEstimado','')}\n"
        f"{acumulado_txt}"
    )
    return msg


async def fetch_lotofacil_official() -> dict:
    """Busca resultado oficial da Lotofácil via servicebus2 (CAIXA)."""
    url = f"{BASE_URL}/lotofacil"

    # Headers mais "humanos" (às vezes evita 403)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer": "https://loterias.caixa.gov.br/",
        "Origin": "https://loterias.caixa.gov.br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    async with httpx.AsyncClient(
        timeout=20.0, headers=headers, follow_redirects=True
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        j = r.json()

    # Campos típicos do servicebus2
    concurso = j.get("numero")
    data_apuracao = j.get("dataApuracao")
    dezenas = j.get("listaDezenas") or []

    prox_numero = j.get("numeroConcursoProximo")
    prox_data = j.get("dataProximoConcurso")
    prox_valor = j.get("valorEstimadoProximoConcurso")

    acumulado = j.get("acumulado")

    sorteio_texto = " ".join([f"[{d}]" for d in dezenas])
    prox_valor_fmt = format_brl(prox_valor)

    payload = {
        "loteria": "lotofacil",
        "concurso": str(concurso) if concurso is not None else "",
        "dataApuracao": data_apuracao or "",
        "sorteio": dezenas,
        "sorteioTexto": sorteio_texto,
        "acumulado": bool(acumulado),
        "proximoConcurso": {
            "numero": str(prox_numero) if prox_numero is not None else "",
            "data": prox_data or "",
            "valorEstimado": prox_valor_fmt,
        },
    }

    payload["mensagem"] = build_message(payload)
    return payload


def get_cache(loteria: str) -> dict | None:
    item = CACHE.get(loteria)
    if not item:
        return None
    if time.time() - item["ts"] > CACHE_TTL_SECONDS:
        return None
    return item["payload"]


def set_cache(loteria: str, payload: dict) -> None:
    CACHE[loteria] = {"ts": time.time(), "payload": payload}


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

    # --- Cache primeiro (resposta rápida) ---
    cached = get_cache(loteria)
    if cached:
        return JSONResponse({"data": cached})

    # --- Busca oficial ---
    try:
        payload = await fetch_lotofacil_official()
        set_cache(loteria, payload)
        return JSONResponse({"data": payload})

    except httpx.HTTPStatusError as e:
        # Se a CAIXA bloquear (403) ou der qualquer erro http,
        # tente retornar o último cache mesmo expirado (se existir)
        last = CACHE.get(loteria, {}).get("payload")
        if last:
            last_copy = dict(last)
            last_copy["alerta"] = f"Consulta CAIXA falhou ({e.response.status_code}). Retornando último resultado em cache."
            last_copy["mensagem"] = (
                last_copy.get("mensagem", "")
                + "\n\n⚠️ *Obs:* Consulta ao portal CAIXA falhou agora; mostrando último resultado disponível."
            )
            return JSONResponse({"data": last_copy})

        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar CAIXA: {e.response.status_code} {e.response.reason_phrase}",
        )

    except Exception as e:
        # Erro genérico
        last = CACHE.get(loteria, {}).get("payload")
        if last:
            last_copy = dict(last)
            last_copy["alerta"] = "Erro inesperado ao consultar CAIXA. Retornando último resultado em cache."
            last_copy["mensagem"] = (
                last_copy.get("mensagem", "")
                + "\n\n⚠️ *Obs:* Erro inesperado na consulta; mostrando último resultado disponível."
            )
            return JSONResponse({"data": last_copy})

        raise HTTPException(status_code=502, detail=f"Erro inesperado: {e}")
