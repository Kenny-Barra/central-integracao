"""
Central Inteligente de Monitoramento
------------------------------------
Integra AwesomeAPI (cotações) + Open-Meteo (clima), persiste no Airtable
e gera alertas automáticos com base em regras configuráveis.
"""
from functools import wraps
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash

import config
from services import cotacoes, clima, airtable, automacao

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("central")

app = Flask(__name__)
app.secret_key = config.APP_API_KEY


@app.template_filter("data_br")
def data_br(valor):
    """Converte ISO 8601 (UTC) para dd/mm/aaaa HH:MM no horário de Brasília."""
    if not valor:
        return ""
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return valor


# ---------- Segurança: rotas de escrita exigem chave de API ----------
def exige_api_key(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        chave = request.headers.get("X-API-Key") or request.form.get("api_key") or request.args.get("api_key")
        if chave != config.APP_API_KEY:
            return jsonify({"erro": "Não autorizado. Informe X-API-Key válido."}), 401
        return f(*args, **kwargs)
    return wrapper


# ---------- Fluxo de integração ----------
def sincronizar() -> dict:
    """1) consome as APIs  2) trata os dados  3) persiste no Airtable  4) roda automação."""
    resumo = {"cotacoes": 0, "clima": 0, "alertas": 0, "erros": []}

    # 1 e 2: coleta + tratamento
    try:
        lista_cotacoes = cotacoes.buscar_cotacoes(config.MOEDAS)
    except requests.RequestException as e:
        lista_cotacoes = []
        resumo["erros"].append(f"AwesomeAPI: {e}")

    lista_clima = clima.buscar_clima_todas(config.CIDADES)
    for c in lista_clima:
        if "erro" in c:
            resumo["erros"].append(f"Open-Meteo ({c['cidade']}): {c['erro']}")
    lista_clima_ok = [c for c in lista_clima if "erro" not in c]

    # 3: persistência no banco no-code
    if airtable.configurado():
        try:
            if lista_cotacoes:
                airtable.criar_registros("Cotacoes", [{
                    "Par": c["par"], "Nome": c["nome"], "Compra": c["compra"], "Venda": c["venda"],
                    "Variacao": c["variacao"], "Maxima": c["maxima"], "Minima": c["minima"],
                    "ColetadoEm": c["coletado_em"], "Fonte": c["fonte"],
                } for c in lista_cotacoes])
                resumo["cotacoes"] = len(lista_cotacoes)

            if lista_clima_ok:
                airtable.criar_registros("Clima", [{
                    "Cidade": c["cidade"], "Temperatura": c["temperatura"], "SensacaoTermica": c["sensacao"],
                    "Umidade": c["umidade"], "Vento": c["vento"], "Chuva": c["chuva"],
                    "Condicao": c["condicao"], "ColetadoEm": c["coletado_em"], "Fonte": c["fonte"],
                } for c in lista_clima_ok])
                resumo["clima"] = len(lista_clima_ok)

            # 4: automação — regras geram alertas
            alertas = automacao.avaliar_cotacoes(lista_cotacoes) + automacao.avaliar_clima(lista_clima_ok)
            if alertas:
                airtable.criar_registros("Alertas", alertas)
            resumo["alertas"] = len(alertas)
        except requests.HTTPError as e:
            resumo["erros"].append(f"Airtable: {e.response.status_code} {e.response.text[:200]}")
    else:
        resumo["erros"].append("Airtable não configurado (defina AIRTABLE_TOKEN e AIRTABLE_BASE_ID no .env).")

    log.info("Sincronização: %s", resumo)
    return resumo


# ---------- Interface web ----------
@app.route("/")
def dashboard():
    dados = {"cotacoes": [], "clima": [], "alertas": [], "erro": None}
    if airtable.configurado():
        try:
            dados["cotacoes"] = airtable.listar_registros("Cotacoes", 30, "ColetadoEm")
            dados["clima"] = airtable.listar_registros("Clima", 30, "ColetadoEm")
            dados["alertas"] = airtable.listar_registros("Alertas", 50, "CriadoEm")
        except requests.RequestException as e:
            dados["erro"] = f"Falha ao ler o Airtable: {e}"
    else:
        dados["erro"] = "Airtable não configurado. Copie .env.example para .env e preencha."

    # Última cotação por par e último clima por cidade (para os cards)
    ultimas = {}
    for c in dados["cotacoes"]:
        ultimas.setdefault(c.get("Par"), c)
    ultimo_clima = {}
    for c in dados["clima"]:
        ultimo_clima.setdefault(c.get("Cidade"), c)

    return render_template(
        "dashboard.html",
        cotacoes=list(ultimas.values()),
        clima=list(ultimo_clima.values()),
        alertas=dados["alertas"],
        historico=dados["cotacoes"][:10],
        erro=dados["erro"],
        limites={"dolar": config.LIMITE_DOLAR, "temp_max": config.LIMITE_TEMP_MAX,
                 "temp_min": config.LIMITE_TEMP_MIN, "chuva": config.LIMITE_CHUVA_MM},
    )


@app.route("/sincronizar", methods=["POST"])
@exige_api_key
def sincronizar_web():
    r = sincronizar()
    msg = f"Sincronizado: {r['cotacoes']} cotações, {r['clima']} registros de clima, {r['alertas']} alertas."
    flash(msg + (" Erros: " + "; ".join(r["erros"]) if r["erros"] else ""), "erro" if r["erros"] else "ok")
    return redirect(url_for("dashboard"))


@app.route("/alertas/<record_id>/resolver", methods=["POST"])
@exige_api_key
def resolver_alerta(record_id):
    airtable.atualizar_registro("Alertas", record_id, {"Resolvido": True})
    flash("Alerta marcado como resolvido.", "ok")
    return redirect(url_for("dashboard"))


# ---------- API REST da própria Central ----------
@app.route("/api/sincronizar", methods=["POST"])
@exige_api_key
def api_sincronizar():
    return jsonify(sincronizar())


@app.route("/api/cotacoes")
def api_cotacoes():
    return jsonify(airtable.listar_registros("Cotacoes", 100, "ColetadoEm"))


@app.route("/api/clima")
def api_clima():
    return jsonify(airtable.listar_registros("Clima", 100, "ColetadoEm"))


@app.route("/api/alertas")
def api_alertas():
    return jsonify(airtable.listar_registros("Alertas", 100, "CriadoEm"))


@app.route("/api/ao-vivo")
def api_ao_vivo():
    """Consulta direta às APIs externas, sem passar pelo banco (útil para depuração)."""
    return jsonify({
        "cotacoes": cotacoes.buscar_cotacoes(config.MOEDAS),
        "clima": clima.buscar_clima_todas(config.CIDADES),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
