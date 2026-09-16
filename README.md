# Central de Monitoramento (Integração de APIs)

Aplicação web em Python + Flask que consome duas APIs públicas (cotações de moedas e clima), trata os dados, grava tudo no Airtable e gera alertas automáticos quando um limite é ultrapassado. Tudo fica em um único painel.

> Trabalho da disciplina **Integração e API**, UniFECAF, 2º semestre.

---

## Índice

1. [Visão geral](#1-visão-geral)
2. [Links do projeto](#2-links-do-projeto)
3. [O problema e a solução](#3-o-problema-e-a-solução)
4. [APIs utilizadas](#4-apis-utilizadas)
5. [Fluxo de integração](#5-fluxo-de-integração)
6. [Tratamento dos dados](#6-tratamento-dos-dados)
7. [Banco de dados (Airtable)](#7-banco-de-dados-airtable)
8. [Automações](#8-automações)
9. [Autenticação e segurança](#9-autenticação-e-segurança)
10. [Dashboard e API própria](#10-dashboard-e-api-própria)
11. [Como executar](#11-como-executar)
12. [LGPD, ética e governança](#12-lgpd-ética-e-governança)
13. [Entregáveis e evidências](#13-entregáveis-e-evidências)
14. [Organização dos arquivos](#14-organização-dos-arquivos)

---

## 1. Visão geral

| | |
|---|---|
| **Stack** | Python 3.12, Flask, Requests |
| **APIs externas** | AwesomeAPI (câmbio) e Open-Meteo (clima) |
| **Banco No-Code** | Airtable, tabelas `Cotacoes`, `Clima` e `Alertas` |
| **Autenticação** | Token Bearer no Airtable; chave `X-API-Key` nas rotas de escrita da aplicação |
| **Automações** | 4 regras: dólar acima do limite, variação brusca, temperatura extrema e chuva forte |
| **Interface** | Dashboard com linha de estado, cotações com tendência, clima com régua de limites, alertas e histórico. Tema claro e escuro |
| **Monitorado** | USD-BRL, EUR-BRL, BTC-BRL e o clima de São Paulo, Rio de Janeiro e Curitiba |

![Dashboard](evidencias/01-dashboard.png)

---

## 2. Links do projeto

- **Vídeo Pitch (YouTube):** _(inserir link)_
- **Demonstração do dashboard (com os dados coletados):** https://claude.ai/code/artifact/5ed94314-b08d-46fe-b489-ef82ea3a6ada
- **Base no Airtable (somente leitura):** https://airtable.com/app78Cm7BMlZ0RrJ0/shrzYA7GZZ82gmY6L
- **Documentação das APIs:** [AwesomeAPI](https://docs.awesomeapi.com.br/api-de-moedas), [Open-Meteo](https://open-meteo.com/en/docs), [Airtable Web API](https://airtable.com/developers/web/api/introduction)

---

## 3. O problema e a solução

**Antes.** Uma equipe financeira ou de operações precisa acompanhar o câmbio (compras importadas, precificação) e o clima (logística, entregas, equipe em campo). Essas informações ficam em sites diferentes, sem histórico e sem nenhum aviso quando algo sai do normal. A pessoa abre várias abas, anota números na mão e decide com dado velho.

**Depois.** A Central faz o ciclo completo em uma sincronização:

1. consome as duas APIs;
2. trata os dados (texto vira número, código WMO vira descrição, cada registro recebe data e fonte);
3. grava no Airtable, formando histórico;
4. aplica as regras de automação e cria alertas por severidade;
5. mostra tudo no dashboard e expõe uma API própria para outros sistemas.

---

## 4. APIs utilizadas

| API | O que fornece | Auth | Por que foi escolhida |
|---|---|---|---|
| **AwesomeAPI (Economia)** | `GET /last/USD-BRL,EUR-BRL,BTC-BRL`: compra, venda, variação do dia, máxima e mínima | Não exige | Brasileira, gratuita e estável. Retorna vários pares em uma chamada. Os valores chegam como texto, o que obriga a tratar os dados |
| **Open-Meteo** | `GET /v1/forecast?latitude&longitude&current=...`: temperatura, sensação, umidade, vento, chuva e código WMO da condição | Não exige | Sem cadastro, JSON enxuto e escolha exata das variáveis. O código numérico precisa ser traduzido |
| **Airtable REST API** | `POST/GET/PATCH /v0/{base}/{tabela}` | Token Bearer | Exigido pelo trabalho. Tem interface visual, automações nativas e limites claros (10 registros por requisição) |

As duas fontes são de áreas totalmente diferentes (financeira e ambiental). É isso que mostra o valor de centralizar: dados que nunca estariam no mesmo sistema passam a ter o mesmo formato, o mesmo histórico e as mesmas regras.

---

## 5. Fluxo de integração

```
┌─────────────┐   GET /last/USD-BRL,...        ┌──────────────────────┐
│  AwesomeAPI │ ─────────────────────────────▶ │                      │
└─────────────┘                                │   Flask (app.py)     │   POST /v0/{base}/Cotacoes
┌─────────────┐   GET /v1/forecast?...         │                      │ ─────────────────────────▶ ┌──────────┐
│ Open-Meteo  │ ─────────────────────────────▶ │  services/cotacoes   │   POST /v0/{base}/Clima    │ Airtable │
└─────────────┘                                │  services/clima      │ ─────────────────────────▶ │          │
                                               │  services/automacao  │   POST /v0/{base}/Alertas  │          │
                                               │  services/airtable   │ ─────────────────────────▶ └────┬─────┘
                                               └──────────┬───────────┘                                 │
                                                          │            GET /v0/{base}/...               │
                                                          ◀─────────────────────────────────────────────┘
                                               ┌──────────▼───────────┐
                                               │ Dashboard  (GET /)   │ ◀── usuário
                                               │ API própria (/api/*) │ ◀── outros sistemas
                                               └──────────────────────┘
```

Uma sincronização é disparada pelo botão do dashboard (`POST /sincronizar`) ou por outro sistema (`POST /api/sincronizar`), o que permite agendar via cron ou GitHub Actions:

1. `services/cotacoes.py` chama a AwesomeAPI e normaliza a resposta.
2. `services/clima.py` chama a Open-Meteo para cada cidade. Se uma cidade falhar, as outras continuam.
3. `services/airtable.py` grava `Cotacoes` e `Clima` em lotes de 10.
4. `services/automacao.py` avalia as regras. Alertas novos vão para `Alertas`; se já existe um aberto com o mesmo título, não duplica.
5. A função devolve um resumo `{cotacoes, clima, alertas, erros}` e registra no log.

Decisões que valem destacar: cada sincronização gera registros novos (nunca sobrescreve), toda chamada externa tem timeout, e cada API tem seu próprio módulo, então trocar de provedor é mexer em um arquivo só.

---

## 6. Tratamento dos dados

| Origem | Como chega | O que é feito |
|---|---|---|
| AwesomeAPI | `"bid": "5.1529"` (texto) | conversão para `float` com tolerância a valor ausente; chave `USDBRL` vira `USD-BRL` |
| Open-Meteo | `"weather_code": 61` | tabela WMO traduz para `"Chuva leve"` e define o símbolo do painel |
| Ambas | nomes de campo diferentes | padronização com `coletado_em` (UTC, ISO 8601) e `fonte` em todo registro |
| Airtable | limite de 10 registros por requisição | gravação em lotes; `typecast` para os campos de seleção |
| Dashboard | datas em UTC | filtro `data_br` mostra `dd/mm/aaaa HH:MM` no horário de Brasília |

---

## 7. Banco de dados (Airtable)

Base **Central de Monitoramento**, três tabelas:

**Cotacoes**

| Campo | Tipo |
|---|---|
| Par (primário) | Texto (`USD-BRL`) |
| Nome | Texto |
| Compra, Venda, Maxima, Minima | Número, 4 casas |
| Variacao | Número, 2 casas (%) |
| ColetadoEm | Data e hora |
| Fonte | Texto (`AwesomeAPI`) |

**Clima**

| Campo | Tipo |
|---|---|
| Cidade (primário) | Texto |
| Temperatura, SensacaoTermica, Vento, Chuva | Número, 1 casa |
| Umidade | Número inteiro (%) |
| Condicao | Texto (descrição WMO em português) |
| ColetadoEm | Data e hora |
| Fonte | Texto (`Open-Meteo`) |

**Alertas**

| Campo | Tipo |
|---|---|
| Titulo (primário) | Texto |
| Tipo | Seleção única (Cotacao, Clima) |
| Severidade | Seleção única (Info, Atencao, Critico) |
| Mensagem | Texto longo |
| Valor, Limite | Número |
| Resolvido | Checkbox |
| CriadoEm | Data e hora |

---

## 8. Automações

Rodam depois de cada sincronização (`services/automacao.py`). Os limites vêm do `.env`.

| Regra | Condição | Severidade |
|---|---|---|
| Dólar alto | `USD-BRL.compra > LIMITE_DOLAR` | Atenção |
| Variação brusca | `abs(variacao) >= 3 %` (a partir de 5 % vira Crítico) | Atenção ou Crítico |
| Temperatura extrema | `temp >= LIMITE_TEMP_MAX` ou `temp <= LIMITE_TEMP_MIN` | Crítico ou Atenção |
| Chuva forte | `chuva >= LIMITE_CHUVA_MM` | Atenção |

Um alerta não é recriado enquanto houver outro aberto com o mesmo título, para não encher a tabela a cada sincronização. Pelo dashboard dá para marcar o alerta como resolvido (grava `Resolvido = true`). Como os alertas ficam no Airtable, também é possível ligar automações nativas da plataforma (e-mail, Slack) sem mexer no código.

---

## 9. Autenticação e segurança

| Onde | Como |
|---|---|
| Airtable | Token pessoal no header `Authorization: Bearer`, com os escopos mínimos e acesso a uma única base |
| Rotas de escrita | `POST /sincronizar`, `POST /api/sincronizar` e `POST /alertas/<id>/resolver` exigem `X-API-Key` (ou o campo `api_key`). Sem a chave a resposta é 401 |
| Rotas de leitura | Públicas, porque não há dado pessoal. Em uso corporativo bastaria aplicar o mesmo decorator |
| Segredos | Só no `.env`, que está no `.gitignore`. O repositório traz o `.env.example` |
| Transporte | HTTPS em todas as chamadas externas |
| Entrada | Cidades e moedas vêm da configuração, não do usuário, então não há como injetar nada nas URLs |

---

## 10. Dashboard e API própria

O dashboard abre com uma linha de estado que resume a situação em palavras ("1 alerta aberto: Dólar acima de R$ 5,00"). Abaixo vêm as cotações com variação, tendência das últimas coletas e spread; o clima com o símbolo da condição, uma régua que mostra onde a temperatura está em relação aos limites de alerta e a tendência; os alertas abertos agrupados por severidade; e o histórico de coletas.

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/` | | Dashboard |
| POST | `/sincronizar` | `api_key` | Sincroniza e volta ao dashboard |
| POST | `/alertas/<id>/resolver` | `api_key` | Marca o alerta como resolvido |
| POST | `/api/sincronizar` | `X-API-Key` | Sincroniza e devolve o resumo em JSON |
| GET | `/api/cotacoes`, `/api/clima`, `/api/alertas` | | Dados gravados no Airtable |
| GET | `/api/ao-vivo` | | Consulta direta às APIs externas, sem gravar |

```bash
curl -X POST http://localhost:5000/api/sincronizar -H "X-API-Key: sua-chave"
# {"alertas": 1, "clima": 3, "cotacoes": 3, "erros": []}
```

---

## 11. Como executar

Precisa de Python 3.10 ou mais novo e uma conta gratuita no Airtable.

```bash
git clone https://github.com/Kenny-Barra/central-integracao.git
cd central-integracao
pip install -r requirements.txt
copy .env.example .env        # Linux/macOS: cp .env.example .env
python app.py
```

Abra <http://localhost:5000>, digite a `APP_API_KEY` no campo do topo e clique em **Sincronizar**.

**Airtable**

1. Crie uma base com as três tabelas da [seção 7](#7-banco-de-dados-airtable), com os campos com o mesmo nome.
2. Gere um token em <https://airtable.com/create/tokens> com os escopos `data.records:read` e `data.records:write` e acesso a essa base.
3. Preencha o `.env`:

| Variável | Para que serve |
|---|---|
| `AIRTABLE_TOKEN` | token do Airtable |
| `AIRTABLE_BASE_ID` | id da base (`app...`) |
| `APP_API_KEY` | chave das rotas de escrita |
| `LIMITE_DOLAR`, `LIMITE_TEMP_MAX`, `LIMITE_TEMP_MIN`, `LIMITE_CHUVA_MM` | limites das automações |
| `CIDADES` | `nome:lat:lon;...` |
| `MOEDAS` | pares da AwesomeAPI separados por vírgula |

---

## 12. LGPD, ética e governança

- **Minimização:** o sistema não coleta dado pessoal, só indicadores públicos, então fica fora do escopo material da LGPD. Se um dia cruzar com dados de clientes, vai precisar de base legal, controle de acesso por perfil e política de retenção.
- **Rastreabilidade:** todo registro tem `Fonte` e `ColetadoEm`.
- **Decisão humana:** os alertas avisam; não compram, não vendem, não fazem nada irreversível.
- **Respeito aos provedores:** poucas chamadas por sincronização, timeouts e nada de consultar em loop.
- **Governança:** um módulo por integração, limites e cidades no `.env`, log de cada sincronização e o `.env` fora do Git.

O detalhamento está na [Parte Teórica](docs/parte-teorica.md).

---

## 13. Entregáveis e evidências

| # | Entregável | Onde está |
|---|---|---|
| 1 | Parte Teórica | [`docs/parte-teorica.md`](docs/parte-teorica.md) |
| 2 | Parte Prática (aplicação, Airtable e automação) | código deste repositório e [`evidencias/`](evidencias/) |
| 3 | Vídeo Pitch | _(inserir link)_ |

---

## 14. Organização dos arquivos

```
central-integracao/
├── README.md
├── app.py                     rotas, fluxo de sincronização e API própria
├── config.py                  lê o .env
├── services/
│   ├── cotacoes.py            AwesomeAPI
│   ├── clima.py               Open-Meteo e mapa de códigos WMO
│   ├── airtable.py            leitura e gravação no Airtable
│   └── automacao.py           regras de alerta
├── templates/dashboard.html
├── static/style.css
├── docs/parte-teorica.md      Parte Teórica
├── evidencias/                prints do sistema funcionando
├── .env.example
└── requirements.txt
```
