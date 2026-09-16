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


@app.template_filter("sparkline")
def sparkline(serie, largura=120, altura=36):
    """Gera os atributos de um sparkline SVG (linha + área) a partir de uma lista de números."""
    pts = [v for v in (serie or []) if v is not None]
    if len(pts) < 2:
        return None
    lo, hi = min(pts), max(pts)
    amp = (hi - lo) or 1
    pad = 3
    passo = (largura - 2 * pad) / (len(pts) - 1)
    coords = [(pad + i * passo, altura - pad - (v - lo) / amp * (altura - 2 * pad)) for i, v in enumerate(pts)]
    linha = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"{coords[0][0]:.1f},{altura} " + linha + f" {coords[-1][0]:.1f},{altura}"
    return {"linha": linha, "area": area, "fim": coords[-1], "w": largura, "h": altura,
            "delta": pts[-1] - pts[0]}


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

            # 4: automação — regras geram alertas (sem duplicar um alerta ainda aberto)
            alertas = automacao.avaliar_cotacoes(lista_cotacoes) + automacao.avaliar_clima(lista_clima_ok)
            abertos = {a.get("Titulo") for a in airtable.listar_registros("Alertas", 100, filtro="NOT({Resolvido})")}
            novos = [a for a in alertas if a["Titulo"] not in abertos]
            if novos:
                airtable.criar_registros("Alertas", novos)
            resumo["alertas"] = len(novos)
            resumo["alertas_ja_abertos"] = len(alertas) - len(novos)
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

    return render_template("dashboard.html", **montar_contexto(dados))


def montar_contexto(dados: dict) -> dict:
    """Agrupa os registros do Airtable no formato que o dashboard exibe."""
    # Última cotação por par + série histórica (mais antiga → mais recente) para o sparkline
    ultimas, series = {}, {}
    for c in dados["cotacoes"]:
        par = c.get("Par")
        ultimas.setdefault(par, c)
        series.setdefault(par, []).append(c.get("Compra"))
    for par, serie in series.items():
        serie.reverse()
        ultimas[par]["serie"] = [v for v in serie if v is not None][-12:]

    # Último clima por cidade + série de temperatura + ícone + posição na régua de limites
    ultimo_clima, series_t = {}, {}
    for c in dados["clima"]:
        cid = c.get("Cidade")
        ultimo_clima.setdefault(cid, c)
        series_t.setdefault(cid, []).append(c.get("Temperatura"))
    lo, hi = config.LIMITE_TEMP_MIN - 10, config.LIMITE_TEMP_MAX + 10
    for cid, c in ultimo_clima.items():
        serie = [v for v in reversed(series_t[cid]) if v is not None][-12:]
        c["serie"] = serie
        c["icone"] = clima.icone(c.get("Condicao", ""))
        t = c.get("Temperatura")
        c["pos"] = None if t is None else max(0, min(100, (t - lo) / (hi - lo) * 100))
        if t is not None and c.get("SensacaoTermica") is not None:
            c["delta_sensacao"] = c["SensacaoTermica"] - t
    regua = {"lo": lo, "hi": hi,
             "min_pct": (config.LIMITE_TEMP_MIN - lo) / (hi - lo) * 100,
             "max_pct": (config.LIMITE_TEMP_MAX - lo) / (hi - lo) * 100}

    # Alertas: abertos agrupados por título (com contagem de ocorrências), depois os resolvidos
    abertos, resolvidos = {}, []
    for a in dados["alertas"]:
        if a.get("Resolvido"):
            resolvidos.append(a)
        elif a.get("Titulo") in abertos:
            abertos[a["Titulo"]]["ocorrencias"] += 1
        else:
            abertos[a["Titulo"]] = {**a, "ocorrencias": 1}
    peso = {"Critico": 0, "Atencao": 1, "Info": 2}
    lista_abertos = sorted(abertos.values(), key=lambda a: peso.get(a.get("Severidade"), 9))
    criticos = sum(1 for a in lista_abertos if a.get("Severidade") == "Critico")

    # Frase de estado: a leitura mais importante da página, em palavras
    if dados["erro"]:
        estado = {"nivel": "crit", "texto": "Falha ao ler o banco de dados", "detalhe": dados["erro"]}
    elif not lista_abertos:
        estado = {"nivel": "ok", "texto": "Todos os indicadores dentro dos limites", "detalhe": ""}
    else:
        n = len(lista_abertos)
        estado = {
            "nivel": "crit" if criticos else "warn",
            "texto": f"{n} alerta{'s' if n != 1 else ''} aberto{'s' if n != 1 else ''}"
                     + (f", {criticos} crítico{'s' if criticos != 1 else ''}" if criticos else ""),
            "detalhe": " · ".join(a["Titulo"] for a in lista_abertos[:3]),
        }

    ultima_coleta = dados["cotacoes"][0].get("ColetadoEm") if dados["cotacoes"] else None
    for c in ultimas.values():
        if c.get("Compra") and c.get("Venda"):
            c["spread"] = c["Venda"] - c["Compra"]

    ordem = {par: i for i, par in enumerate(config.MOEDAS)}
    return {
        "cotacoes": sorted(ultimas.values(), key=lambda c: ordem.get(c.get("Par"), 99)),
        "clima": list(ultimo_clima.values()),
        "abertos": lista_abertos,
        "resolvidos": resolvidos[:6],
        "estado": estado,
        "regua": regua,
        "historico": dados["cotacoes"][:12],
        "erro": dados["erro"],
        "kpis": {"abertos": len(lista_abertos), "criticos": criticos, "ultima": ultima_coleta,
                 "total_alertas": len(dados["alertas"])},
        "fontes": [
            {"nome": "AwesomeAPI", "ok": bool(dados["cotacoes"])},
            {"nome": "Open-Meteo", "ok": bool(dados["clima"])},
            {"nome": "Airtable", "ok": airtable.configurado() and not dados["erro"]},
        ],
        "limites": {"dolar": config.LIMITE_DOLAR, "temp_max": config.LIMITE_TEMP_MAX,
                    "temp_min": config.LIMITE_TEMP_MIN, "chuva": config.LIMITE_CHUVA_MM},
    }


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
