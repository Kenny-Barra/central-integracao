"""Regras de automação: avaliam os dados integrados e geram alertas no Airtable."""
from datetime import datetime, timezone
from config import LIMITE_DOLAR, LIMITE_TEMP_MAX, LIMITE_TEMP_MIN, LIMITE_CHUVA_MM


def _agora():
    return datetime.now(timezone.utc).isoformat()


def avaliar_cotacoes(cotacoes: list[dict]) -> list[dict]:
    """Regra 1: dólar acima do limite. Regra 2: variação diária >= 3%."""
    alertas = []
    for c in cotacoes:
        if c["par"] == "USD-BRL" and c["compra"] and c["compra"] > LIMITE_DOLAR:
            alertas.append({
                "Titulo": f"Dólar acima de R$ {LIMITE_DOLAR:.2f}",
                "Tipo": "Cotacao",
                "Severidade": "Atencao",
                "Mensagem": f"USD-BRL cotado a R$ {c['compra']:.4f} (variação {c['variacao']}%).",
                "Valor": c["compra"],
                "Limite": LIMITE_DOLAR,
                "CriadoEm": _agora(),
            })
        if c["variacao"] is not None and abs(c["variacao"]) >= 3:
            alertas.append({
                "Titulo": f"{c['par']} variou {c['variacao']:+.2f}% no dia",
                "Tipo": "Cotacao",
                "Severidade": "Critico" if abs(c["variacao"]) >= 5 else "Atencao",
                "Mensagem": f"{c['nome']}: compra R$ {c['compra']}, máxima {c['maxima']}, mínima {c['minima']}.",
                "Valor": c["variacao"],
                "Limite": 3,
                "CriadoEm": _agora(),
            })
    return alertas


def avaliar_clima(climas: list[dict]) -> list[dict]:
    """Regra 3: temperatura extrema. Regra 4: chuva forte."""
    alertas = []
    for c in climas:
        if "erro" in c or c.get("temperatura") is None:
            continue
        t = c["temperatura"]
        if t >= LIMITE_TEMP_MAX:
            alertas.append(_alerta_clima(c, f"Calor extremo em {c['cidade']}", "Critico", t, LIMITE_TEMP_MAX))
        elif t <= LIMITE_TEMP_MIN:
            alertas.append(_alerta_clima(c, f"Frio intenso em {c['cidade']}", "Atencao", t, LIMITE_TEMP_MIN))
        if (c.get("chuva") or 0) >= LIMITE_CHUVA_MM:
            alertas.append(_alerta_clima(c, f"Chuva forte em {c['cidade']}", "Atencao", c["chuva"], LIMITE_CHUVA_MM))
    return alertas


def _alerta_clima(c, titulo, sev, valor, limite):
    return {
        "Titulo": titulo,
        "Tipo": "Clima",
        "Severidade": sev,
        "Mensagem": f"{c['cidade']}: {c['temperatura']}°C, sensação {c['sensacao']}°C, "
                    f"umidade {c['umidade']}%, chuva {c['chuva']} mm ({c['condicao']}).",
        "Valor": valor,
        "Limite": limite,
        "CriadoEm": _agora(),
    }
