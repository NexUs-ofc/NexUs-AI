# Painel do administrador

Rotas que o painel do administrador (React) consome para montar a página da IA. São só dados em JSON: a
apresentação é do painel. O BI IA responde nas mesmas rotas e no mesmo formato, para o painel desenhar as
duas páginas com os mesmos componentes.

## Autenticação

Uma chave só, a mesma em todos os serviços do NexUs (Auth, Core, Notify, IA e BI IA). O painel pede a
chave no login e a manda em todas as requisições:

```
X-Admin-Key: <ADMIN_API_KEY>
```

| Situação | Resposta |
| --- | --- |
| Chave certa | `200` |
| Chave ausente ou errada | `401` |
| `ADMIN_API_KEY` não configurada no servidor | `503` |

A chave do painel não abre o `/chat`, e a `API_KEY` do aplicativo não abre o painel.

## Rotas

| Método | Rota | Fonte | O que devolve |
| --- | --- | --- | --- |
| `GET` | `/admin/session` | — | Confirma a chave no login: `{"servico", "autenticado", "verificado_em"}` |
| `GET` | `/admin/metrics?dias=7` | Mongo | Resumo, desempenho, leitura de nota, custo e qualidade |
| `GET` | `/admin/report?dias=7` | Mongo | O período contra o período anterior de mesmo tamanho |
| `GET` | `/admin/langsmith?dias=7` | LangSmith | Execuções por dia, p50/p99 por chain e por agente, feedback, custo em real |
| `GET` | `/admin/dependencies` | — | Estado de MongoDB, PostgreSQL, Qdrant, Groq e LangSmith |

`dias` vai de 1 a 90. `/admin/metrics` e `/admin/report` respondem em segundos; `/admin/langsmith` pagina a
API do LangSmith e pode levar dezenas de segundos, então o painel deve carregá-la à parte.

Os dias são contados no horário de Brasília. Instantes vêm em ISO-8601.

## `/admin/metrics`

```json
{
  "servico": "ceris-ia",
  "janela": {"inicio": "...", "fim": "...", "dias": 7},
  "resumo": {
    "execucoes": 3800, "p50_e2e_s": 1.4, "p95_e2e_s": 2.8, "custo_usd": 3.8,
    "taxa_erro_pct": 2.0, "devolucoes_juiz_pct": 8.0
  },
  "desempenho": {
    "latencia_por_rota": [{"rota": "eventos", "execucoes": 760, "erros": 3, "p50_s": 1.6, "p95_s": 3.4}],
    "latencia_por_no": [{
      "rota": "eventos", "execucoes": 760, "total_s": 1.9,
      "etapas_s": {"roteador": 0.2, "agente": 1.2, "juiz": 0.3, "guardrails": 0.1, "orquestrador": 0.1}
    }]
  },
  "leitura_nota": {"leituras": 600, "sucesso": 588, "taxa_sucesso_pct": 98.0, "tempo_medio_s": 1.4, "p95_s": 2.1},
  "custo": {
    "tokens": {
      "limite_diario": 200000, "total_entrada": 665000, "total_saida": 285000,
      "pico": {"dia": "2026-10-20", "total": 152500, "pct_do_limite": 76.25},
      "dias": [{"dia": "2026-10-14", "entrada": 90000, "saida": 40000, "total": 130000,
                "por_rota": {"estoque": {"entrada": 30000, "saida": 12000}}}]
    },
    "custo": {"total_usd": 3.8, "por_modelo": {"openai/gpt-oss-20b": 3.8},
              "dias": [{"dia": "2026-10-14", "total_usd": 0.5, "por_modelo": {"openai/gpt-oss-20b": 0.5}}]},
    "erros_de_cota": {"total_24h": 6, "total_janela": 28, "por_hora": [{"hora": "2026-10-20T09:00:00-03:00", "quantidade": 2}]}
  },
  "qualidade": {
    "juiz": {"total": 3800, "aprovado": {"quantidade": 3420, "pct": 90.0},
             "devolvido": {"quantidade": 304, "pct": 8.0}, "revertido": {"quantidade": 76, "pct": 2.0}},
    "guardrails": {"execucoes": 3800, "entrada": 38, "saida": 19, "total": 57, "pct": 1.5},
    "ferramentas": [{"tool": "get_stock", "chamadas": 1520, "erros": 15, "taxa_erro_pct": 0.99, "media_ms": 180, "p95_ms": 420}]
  }
}
```

- **Etapas por rota** são médias: somadas, dão a média ponta a ponta da rota. Agente, juiz e orquestrador
  podem rodar duas vezes numa requisição (devolução do juiz); entra a soma.
- **Juiz**: uma decisão por leitura. `aprovado` de primeira, `devolvido` quando a reprovação se confirmou e
  `revertido` quando a segunda opinião absolveu a reprovação. `devolucoes_juiz_pct` é devolvido sobre o total.
- **Cota**: `erros_de_cota` conta requisições que terminaram em 429 do Groq. O 429 que o retry do cliente
  absorveu vira latência e não entra aqui.
- **Leitura de nota** não entra no volume, na latência nem na taxa de erro do chat.
- Métricas gravadas antes desta versão não têm decisão do juiz, bloqueio de guardrail nem modelo: contam
  como sem decisão, sem bloqueio e no modelo padrão.

## `/admin/report`

```json
{
  "gerado_em": "...",
  "periodo_atual": {"inicio": "...", "fim": "..."},
  "periodo_anterior": {"inicio": "...", "fim": "..."},
  "indicadores": [
    {"indicador": "volume", "unidade": "execucoes", "atual": 3800, "anterior": 3460, "variacao": 9.83, "variacao_em": "pct"},
    {"indicador": "taxa_erro_pct", "unidade": "%", "atual": 2.0, "anterior": 2.5, "variacao": -0.5, "variacao_em": "pontos"}
  ],
  "rotas_mais_lentas": [{"rota": "eventos", "p95_s": 3.4}],
  "tools_com_mais_erro": [{"tool": "tavily_search", "chamadas": 760, "erros": 30, "taxa_erro_pct": 3.95}],
  "consumo": {"tokens_entrada": 665000, "tokens_saida": 285000, "pico_diario": {"dia": "...", "total": 152500}, "limite_diario": 200000},
  "leitura_nota": {"leituras": 600, "taxa_sucesso_pct": 98.0},
  "juiz": {"total": 3800}
}
```

Os indicadores são volume, `latencia_p95_e2e_s`, `custo_usd`, `taxa_erro_pct` e `devolucoes_juiz_pct`.
Volume, latência e custo variam em percentual; taxa de erro e devolução do juiz, que já são percentuais,
variam em pontos. Sem período anterior, a variação percentual vem `null`.

## `/admin/langsmith`

Os campos de antes continuam (requisições, tempo total, custo em dólar e em real pela PTAX, projeção para
100 e 1000 usuários, ROI e últimos erros) e entram:

- `execucoes_por_dia`: `[{"dia", "execucoes", "erros", "taxa_erro_pct"}]`
- `etapas` (chains do grafo) e `agentes`: cada item com `p50_s`, `p95_s` e `p99_s`, além de média e mediana
- `feedback`: `{"disponivel", "total", "por_chave": {"<chave>": {"avaliacoes", "media"}}}`. Sem avaliação
  gravada, `total` é zero.

Parâmetros: `dias`, `mensagens_semana` (projeção), `economia_mensal_brl` (ROI) e `projeto`.

## Variáveis

| Variável | Uso |
| --- | --- |
| `ADMIN_API_KEY` | Chave do painel. `TRACING_API_KEY` continua aceita no lugar. |
| `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGSMITH_WORKSPACE_ID` | Seção do LangSmith |

```sh
curl -H 'X-Admin-Key: <ADMIN_API_KEY>' 'http://localhost:8000/admin/metrics?dias=7'
```
