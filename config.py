"""Configuração central: carrega variáveis do .env e expõe constantes."""
import os
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
APP_API_KEY = os.getenv("APP_API_KEY", "dev-key")

LIMITE_DOLAR = float(os.getenv("LIMITE_DOLAR", "5.50"))
LIMITE_TEMP_MAX = float(os.getenv("LIMITE_TEMP_MAX", "35"))
LIMITE_TEMP_MIN = float(os.getenv("LIMITE_TEMP_MIN", "5"))
LIMITE_CHUVA_MM = float(os.getenv("LIMITE_CHUVA_MM", "10"))

MOEDAS = [m.strip() for m in os.getenv("MOEDAS", "USD-BRL,EUR-BRL,BTC-BRL").split(",") if m.strip()]


def _parse_cidades(raw: str):
    cidades = []
    for item in raw.split(";"):
        partes = item.strip().split(":")
        if len(partes) == 3:
            nome, lat, lon = partes
            cidades.append({"nome": nome.strip(), "lat": float(lat), "lon": float(lon)})
    return cidades


CIDADES = _parse_cidades(
    os.getenv("CIDADES", "São Paulo:-23.55:-46.63;Rio de Janeiro:-22.91:-43.17;Curitiba:-25.43:-49.27")
)
