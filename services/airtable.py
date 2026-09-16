"""Camada de persistência: Airtable (banco no-code) via API REST com token Bearer."""
import requests
from config import AIRTABLE_TOKEN, AIRTABLE_BASE_ID

API_URL = "https://api.airtable.com/v0"
TIMEOUT = 15


def _headers():
    return {"Authorization": f"Bearer {AIRTABLE_TOKEN}", "Content-Type": "application/json"}


def _url(tabela: str) -> str:
    return f"{API_URL}/{AIRTABLE_BASE_ID}/{tabela}"


def configurado() -> bool:
    return bool(AIRTABLE_TOKEN and AIRTABLE_BASE_ID)


def criar_registros(tabela: str, registros: list[dict]) -> list[dict]:
    """Insere registros em lotes de 10 (limite da API do Airtable)."""
    criados = []
    for i in range(0, len(registros), 10):
        lote = registros[i:i + 10]
        payload = {"records": [{"fields": r} for r in lote], "typecast": True}
        resp = requests.post(_url(tabela), json=payload, headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        criados.extend(resp.json().get("records", []))
    return criados


def listar_registros(tabela: str, max_registros: int = 50, ordenar_por: str | None = None,
                     desc: bool = True, filtro: str | None = None) -> list[dict]:
    """Lista registros de uma tabela, achatando o campo 'fields'."""
    params: dict = {"maxRecords": max_registros}
    if ordenar_por:
        params["sort[0][field]"] = ordenar_por
        params["sort[0][direction]"] = "desc" if desc else "asc"
    if filtro:
        params["filterByFormula"] = filtro
    resp = requests.get(_url(tabela), params=params, headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return [{"id": r["id"], **r.get("fields", {})} for r in resp.json().get("records", [])]


def atualizar_registro(tabela: str, record_id: str, campos: dict) -> dict:
    resp = requests.patch(f"{_url(tabela)}/{record_id}", json={"fields": campos},
                          headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()
