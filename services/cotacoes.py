"""Integração com a AwesomeAPI (cotações de moedas). API pública, sem autenticação."""
from datetime import datetime, timezone
import requests

BASE_URL = "https://economia.awesomeapi.com.br/last/"
TIMEOUT = 10


def buscar_cotacoes(pares: list[str]) -> list[dict]:
    """Consulta as cotações e devolve uma lista de dicts já tratados/normalizados."""
    resp = requests.get(BASE_URL + ",".join(pares), timeout=TIMEOUT)
    resp.raise_for_status()
    dados = resp.json()

    resultado = []
    for par in pares:
        chave = par.replace("-", "")
        item = dados.get(chave)
        if not item:
            continue
        resultado.append(_normalizar(par, item))
    return resultado


def _normalizar(par: str, item: dict) -> dict:
    """Converte strings da API em números e padroniza nomes de campos."""
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "par": par,
        "nome": item.get("name", par),
        "compra": num(item.get("bid")),
        "venda": num(item.get("ask")),
        "variacao": num(item.get("pctChange")),
        "maxima": num(item.get("high")),
        "minima": num(item.get("low")),
        "coletado_em": datetime.now(timezone.utc).isoformat(),
        "fonte": "AwesomeAPI",
    }
