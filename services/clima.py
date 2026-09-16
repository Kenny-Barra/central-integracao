"""Integração com a Open-Meteo (clima). API pública, sem autenticação."""
from datetime import datetime, timezone
import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10

# Tabela de códigos WMO -> descrição em português
CODIGOS_WMO = {
    0: "Céu limpo", 1: "Predominantemente limpo", 2: "Parcialmente nublado", 3: "Nublado",
    45: "Neblina", 48: "Neblina com geada",
    51: "Garoa leve", 53: "Garoa moderada", 55: "Garoa intensa",
    61: "Chuva leve", 63: "Chuva moderada", 65: "Chuva forte",
    71: "Neve leve", 73: "Neve moderada", 75: "Neve forte",
    80: "Pancadas de chuva leves", 81: "Pancadas de chuva", 82: "Pancadas de chuva fortes",
    95: "Tempestade", 96: "Tempestade com granizo", 99: "Tempestade forte com granizo",
}


def buscar_clima(cidade: dict) -> dict:
    """Consulta o clima atual de uma cidade e devolve um dict normalizado."""
    params = {
        "latitude": cidade["lat"],
        "longitude": cidade["lon"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "timezone": "America/Sao_Paulo",
    }
    resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    atual = resp.json().get("current", {})

    codigo = atual.get("weather_code")
    return {
        "cidade": cidade["nome"],
        "temperatura": atual.get("temperature_2m"),
        "sensacao": atual.get("apparent_temperature"),
        "umidade": atual.get("relative_humidity_2m"),
        "vento": atual.get("wind_speed_10m"),
        "chuva": atual.get("precipitation"),
        "condicao": CODIGOS_WMO.get(codigo, f"Código {codigo}"),
        "coletado_em": datetime.now(timezone.utc).isoformat(),
        "fonte": "Open-Meteo",
    }


def buscar_clima_todas(cidades: list[dict]) -> list[dict]:
    """Consulta todas as cidades; falhas individuais não derrubam o lote inteiro."""
    resultado = []
    for c in cidades:
        try:
            resultado.append(buscar_clima(c))
        except requests.RequestException as e:
            resultado.append({"cidade": c["nome"], "erro": str(e)})
    return resultado


# Grupos de códigos WMO -> símbolo do painel (ícones de linha definidos no template)
_ICONES = {
    "sol": {0}, "sol-nuvem": {1, 2}, "nuvem": {3}, "neblina": {45, 48},
    "garoa": {51, 53, 55}, "chuva": {61, 63, 65, 80, 81, 82},
    "neve": {71, 73, 75}, "tempestade": {95, 96, 99},
}
_ICONE_POR_TEXTO = {CODIGOS_WMO[c]: nome for nome, codigos in _ICONES.items() for c in codigos}


def icone(condicao: str) -> str:
    """Nome do ícone para uma descrição de condição gravada no banco."""
    return _ICONE_POR_TEXTO.get(condicao, "nuvem")
