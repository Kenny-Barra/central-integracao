# Parte Teórica – Análise e Discussão

**Projeto:** Central Inteligente de Monitoramento: Integrando APIs para Automatizar Processos e Gerar Insights
**Disciplina:** Integração e API – UNIFECAF, 2º semestre
**Aluno:** Kenedy Pereira

---

## 1. Contextualização do problema

Organizações modernas operam com dezenas de ferramentas digitais especializadas: um sistema para clientes, outro para indicadores, aplicativos distintos para notificações e plataformas separadas para documentos. Cada uma dessas ferramentas resolve bem o seu problema isolado, mas a soma delas cria um problema novo: a **fragmentação da informação**.

Na prática, isso significa que um colaborador precisa abrir várias telas para executar tarefas simples, copiar dados manualmente entre sistemas e cruzar informações "de cabeça". As consequências são conhecidas: aumento do tempo gasto em atividades operacionais, maior incidência de erros de digitação e interpretação, retrabalho e, principalmente, decisões tomadas com informação desatualizada ou incompleta.

Para tornar o problema concreto, este projeto adota o cenário de uma **equipe financeira e de operações** que precisa acompanhar diariamente dois fatores externos que afetam diretamente o negócio:

- **Câmbio:** o valor do dólar e do euro impacta compras de insumos importados, precificação e contratos; o bitcoin foi incluído como ativo de alta volatilidade para demonstrar regras de variação.
- **Clima:** temperatura extrema e chuva forte afetam logística, entregas, consumo de energia e segurança de equipes em campo.

Hoje essas informações são consultadas em sites diferentes, sem histórico consolidado e sem qualquer aviso automático quando um limite relevante é ultrapassado.

## 2. Descrição da solução proposta

A **Central Inteligente de Monitoramento** é uma aplicação web que centraliza a coleta, o tratamento, o armazenamento e a visualização desses dados, além de executar automações sobre eles. Seus componentes são:

1. **Camada de integração** (`services/cotacoes.py` e `services/clima.py`): consome as APIs externas e converte as respostas em um formato interno padronizado.
2. **Camada de persistência** (`services/airtable.py`): grava e lê os dados em um banco no-code (Airtable), que também funciona como interface administrativa e ponto de extensão para automações nativas da plataforma.
3. **Camada de automação** (`services/automacao.py`): avalia regras configuráveis e gera alertas classificados por tipo e severidade.
4. **Camada de apresentação** (`app.py` + `templates/`): dashboard web com cards de cotação e clima, tabela de alertas com possibilidade de resolução e histórico.
5. **API própria** (`/api/*`): permite que outros sistemas da empresa consumam os dados já consolidados, fechando o ciclo de integração.

A solução foi construída em Python com Flask por ser uma stack leve, legível e adequada a projetos de integração, em que o valor está na orquestração das chamadas e no tratamento dos dados, não em uma interface complexa.

## 3. APIs utilizadas e justificativa da escolha

### 3.1 AwesomeAPI – Cotações de moedas

- **Endpoint:** `GET https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,BTC-BRL`
- **Autenticação:** não exigida no plano público.
- **Dados obtidos:** compra (`bid`), venda (`ask`), variação percentual (`pctChange`), máxima e mínima do dia.
- **Justificativa:** é uma API brasileira, gratuita, com alta disponibilidade e documentação clara. Retorna múltiplos pares em uma única chamada, o que reduz o número de requisições. Os dados chegam como *strings*, o que exige tratamento explícito, um bom exemplo didático de manipulação de dados.

### 3.2 Open-Meteo – Dados meteorológicos

- **Endpoint:** `GET https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&current=...`
- **Autenticação:** não exigida para uso não comercial.
- **Dados obtidos:** temperatura, sensação térmica, umidade, vento, precipitação e código de condição do tempo (padrão WMO).
- **Justificativa:** não exige cadastro nem chave, permite selecionar exatamente as variáveis desejadas e devolve JSON compacto. O código WMO numérico precisa ser traduzido para texto legível, outro ponto de tratamento de dados.

### 3.3 Airtable REST API – Banco de dados no-code

- **Endpoint:** `https://api.airtable.com/v0/{baseId}/{tabela}`
- **Autenticação:** *Personal Access Token* (Bearer) com escopos `data.records:read` e `data.records:write`.
- **Justificativa:** requisito do trabalho; além disso oferece interface visual gratuita para inspeção dos dados, automações nativas (e-mail, Slack, webhooks) e uma API REST simples, com limites claros (10 registros por requisição, 5 requisições/segundo) que precisam ser respeitados no código.

### 3.4 Por que essas duas APIs juntas?

Elas representam **domínios completamente diferentes** (financeiro e ambiental), o que torna evidente o valor da centralização: dados que jamais estariam no mesmo sistema passam a coexistir em um único painel e em um único banco, com o mesmo padrão de carimbo de tempo e fonte.

## 4. Fluxo de integração entre os sistemas

O fluxo é disparado pelo usuário (botão "Sincronizar") ou por um sistema externo (`POST /api/sincronizar`), o que permite agendamento via cron, GitHub Actions ou qualquer orquestrador.

```
Usuário / agendador
        │  POST /sincronizar (com chave)
        ▼
┌──────────────────────────────────────────────────────────┐
│ app.sincronizar()                                        │
│                                                          │
│  1. cotacoes.buscar_cotacoes()  ──▶ AwesomeAPI (HTTPS)   │
│  2. clima.buscar_clima_todas()  ──▶ Open-Meteo (HTTPS)   │
│        └─ para cada cidade; erro isolado não interrompe  │
│  3. tratamento/normalização (float, WMO→texto, UTC)      │
│  4. airtable.criar_registros("Cotacoes" | "Clima")       │
│  5. automacao.avaliar_*()  ──▶ lista de alertas          │
│  6. airtable.criar_registros("Alertas")                  │
│  7. resumo {cotacoes, clima, alertas, erros}             │
└──────────────────────────────────────────────────────────┘
        │
        ▼
Dashboard (GET /) lê o Airtable e renderiza
API própria (GET /api/*) expõe os dados a outros sistemas
```

Decisões relevantes de projeto:

- **Idempotência parcial:** cada sincronização gera novos registros (histórico), nunca sobrescreve; o dashboard exibe o mais recente por par/cidade.
- **Tolerância a falhas:** cada fonte é envolvida em `try/except`; uma API fora do ar gera uma entrada em `erros`, mas as demais continuam.
- **Lotes:** a gravação no Airtable é feita em lotes de 10, respeitando o limite da API.
- **Timeouts:** todas as chamadas externas têm limite de 10–15 s para evitar travamentos.

## 5. Estratégia de autenticação e segurança

| Camada | Mecanismo |
|---|---|
| Airtable | Token pessoal (PAT) enviado no header `Authorization: Bearer`, com escopos mínimos e acesso restrito a uma única base. |
| Central (escrita) | Header `X-API-Key` (ou campo de formulário) validado pelo decorator `exige_api_key`; sem ele as rotas de sincronização e resolução retornam **401**. |
| Central (leitura) | Pública, pois os dados são indicadores públicos sem informação pessoal. Em cenário corporativo bastaria aplicar o mesmo decorator. |
| Segredos | Vivem apenas no arquivo `.env`, listado no `.gitignore`; o repositório publica somente `.env.example`. |
| Transporte | Todas as APIs são consumidas via HTTPS. |
| Entrada | Parâmetros de cidades/moedas vêm de configuração, não de input do usuário, eliminando injeção nas URLs externas. |

Melhorias possíveis para produção: autenticação de usuários (OAuth/OIDC), *rate limiting* nas rotas da Central, rotação periódica do token e uso de um cofre de segredos.

## 6. Forma de armazenamento e manipulação dos dados

**Modelo de dados (Airtable):**

| Tabela | Finalidade | Campos principais |
|---|---|---|
| `Cotacoes` | Histórico de câmbio | Par, Nome, Compra, Venda, Variacao, Maxima, Minima, ColetadoEm, Fonte |
| `Clima` | Histórico meteorológico | Cidade, Temperatura, SensacaoTermica, Umidade, Vento, Chuva, Condicao, ColetadoEm, Fonte |
| `Alertas` | Saída da automação | Titulo, Tipo, Severidade, Mensagem, Valor, Limite, Resolvido, CriadoEm |

**Tratamento aplicado antes de persistir:**

- Conversão de strings numéricas (`"5.1529"`) em `float`, com tolerância a valores ausentes.
- Tradução do código WMO (ex.: `61`) para descrição em português ("Chuva leve").
- Padronização de nomes de campos entre as duas fontes (`coletado_em`, `fonte`).
- Carimbo de tempo em UTC (ISO 8601), convertido para o fuso de São Paulo pelo próprio Airtable na exibição.
- Registro da **fonte** em cada linha, garantindo rastreabilidade (linhagem do dado).

**Leitura:** o dashboard consulta as tabelas ordenadas por data decrescente e agrupa em memória o último valor por par/cidade, evitando lógica complexa de consulta no banco.

## 7. Aspectos de LGPD, ética e governança das integrações

### LGPD

A solução foi desenhada com o princípio da **minimização**: não coleta, armazena nem trafega dados pessoais, apenas indicadores econômicos e meteorológicos públicos. Isso a coloca fora do escopo material da LGPD. Ainda assim, caso o projeto evolua para incluir dados de clientes (ex.: cruzar clima com endereços de entrega), seriam necessários: base legal definida (execução de contrato ou legítimo interesse), registro das operações de tratamento, controle de acesso por perfil, política de retenção e descarte, e canal para exercício de direitos dos titulares.

### Ética

- **Transparência:** cada registro carrega a fonte e o horário de coleta; o usuário sabe de onde o dado veio.
- **Uso responsável:** os alertas são informativos e não tomam decisões automáticas de compra/venda; a decisão permanece humana.
- **Respeito aos provedores:** o código respeita os limites de uso das APIs gratuitas (poucas chamadas por sincronização, timeouts, sem *polling* agressivo).

### Governança das integrações

- **Catálogo de integrações:** cada API tem um módulo próprio em `services/`, com URL, autenticação e formato documentados, fácil de auditar e substituir.
- **Configuração externa:** limites, cidades e moedas ficam no `.env`, permitindo mudar regras sem alterar código.
- **Observabilidade:** logs estruturados de cada sincronização (quantidades e erros) e resumo retornado pela API.
- **Controle de mudanças:** versionamento no Git com `.env` fora do repositório.
- **Ciclo de vida dos dados:** o Airtable permite visualizações, filtros e exclusão em massa; recomenda-se política de retenção (ex.: 90 dias) para o histórico.
- **Dependência de terceiros:** o risco de descontinuidade das APIs gratuitas é mitigado pela arquitetura em módulos: trocar de provedor exige alterar apenas um arquivo.

## 8. Conclusão

O projeto demonstra, em escala reduzida, o ciclo completo de uma integração corporativa: consumir fontes heterogêneas, normalizar, persistir em um repositório único, automatizar reações e expor os dados consolidados para pessoas e sistemas. A escolha de APIs públicas e de um banco no-code reduz o custo de entrada, enquanto a separação em camadas e as práticas de segurança e governança mostram como a mesma arquitetura escalaria para um cenário real.

## Referências

- AwesomeAPI. *API de Moedas*. Disponível em: <https://docs.awesomeapi.com.br/api-de-moedas>.
- Open-Meteo. *Weather Forecast API*. Disponível em: <https://open-meteo.com/en/docs>.
- Airtable. *Web API Reference*. Disponível em: <https://airtable.com/developers/web/api/introduction>.
- BRASIL. *Lei nº 13.709, de 14 de agosto de 2018 (LGPD)*.
- Flask. *Documentation*. Disponível em: <https://flask.palletsprojects.com/>.
