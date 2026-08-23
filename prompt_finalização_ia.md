# Ceris.AI — Investigação de Inconsistências no ms-ia

## CONTEXTO QUE VOCÊ JÁ TEM (não precisa redescobrir)

- O projeto passou por uma leva grande de correções recentes: `entities/`
  virou `model/`, `.env` foi centralizado em `app/config.py`, o modelo Groq
  mudou de `llama-3.3-70b-versatile` para `openai/gpt-oss-20b`, e o schema
  do Postgres foi corrigido para bater com o banco real — `pantry_item`
  agora usa `profile_id` (não `household_account_id`), sem coluna
  `is_expired`, com `minimum_quantity` numa tabela separada
  (`pantry_product_setting`).
- **Ponto de atenção específico:** as tools de `pg_tools.py` (`get_stock`,
  `get_expired_products`, `get_missing_products`, `get_category_info`,
  `get_brand_info`) foram renomeadas para receber `profile_id` como
  parâmetro. Só que o `flow.py` (funções `agente_estoque` e
  `agente_receitas`) ainda monta a mensagem enviada ao LLM usando o marcador
  de texto `HOUSEHOLD_ACCOUNT_ID={household_id}` — e os prompts
  (`prompt_estoque.py`, `prompt_receitas.py`) não foram atualizados para
  saber que esse valor deve virar o argumento `profile_id` ao chamar a
  tool. Essa é a HIPÓTESE PRIORITÁRIA: o LLM está recebendo um dado com um
  nome e uma tool que espera outro nome, e provavelmente não está
  conseguindo (ou não com confiança) inferir que são a mesma coisa —
  resultando em "não chamei a tool porque não tenho profile_id" e o agente
  volta a perguntar o que já deveria saber.

## OBJETIVO

Investigar, na ordem abaixo, cada hipótese — confirmando ou descartando com
evidência real (log, print temporário, resposta da API) antes de aplicar
qualquer correção. Não corrija nada "no escuro"; primeiro prove a causa.

---

## HIPÓTESE 1 — Descompasso `HOUSEHOLD_ACCOUNT_ID` (mensagem) vs `profile_id` (tool)

1. Abra `app/schemas/flow.py`, funções `agente_estoque` e `agente_receitas`.
   Confirme que a mensagem montada usa `HOUSEHOLD_ACCOUNT_ID=...`.
2. Abra `app/tools/pg_tools.py` e confirme que todas as tools esperam
   `profile_id` (não `household_account_id`).
3. Abra `app/core/prompts/prompt_estoque.py` e `prompt_receitas.py` e
   verifique se em algum lugar do texto do prompt existe instrução
   explicando que `HOUSEHOLD_ACCOUNT_ID` recebido na entrada deve ser usado
   como `profile_id` ao chamar as tools de estoque. Se essa instrução não
   existir, essa é a causa confirmada.
4. Teste isolado: mande a mensagem
   `"Qual é o meu estoque?"` com `household_account_id: 3` e observe (via
   log temporário dentro de `get_stock` em `pg_tools.py`, um `print` antes
   do `return`, removido depois do teste) se a tool é chamada e com qual
   valor de `profile_id`.
5. **Correção, se confirmado:** o jeito mais simples e que não muda
   arquitetura é ajustar o texto da mensagem em `flow.py` para já emitir o
   nome que a tool espera: trocar `HOUSEHOLD_ACCOUNT_ID={household_id}` por
   `PROFILE_ID={household_id}` nas funções `agente_estoque` e
   `agente_receitas`, e atualizar as referências a `HOUSEHOLD_ACCOUNT_ID`
   dentro de `prompt_estoque.py`/`prompt_receitas.py` para `PROFILE_ID`
   (ambos os pontos, prompt e código, têm que falar a mesma língua).

---

## HIPÓTESE 2 — Roteador sem categoria para perguntas de identidade/perfil

1. Abra `app/core/prompts/prompt_roteador.py`. Confirme que as únicas
   categorias são `faq`, `receitas`, `estoque`, `eventos`, `fallback`.
2. Teste isolado: mande `"Quem sou eu?"` e registre (log temporário no nó
   `roteador` de `flow.py`, no `print(state["rota"])` logo após a
   atribuição) qual rota o roteador escolheu.
3. Se cair em `faq`: o roteador está generalizando errado porque não há
   exemplo de few-shot pra esse tipo de pergunta, e `faq` provavelmente foi
   o "menos errado" que o modelo achou. Não crie uma rota nova — hoje não
   existe nenhum agente que saiba responder sobre o perfil do usuário
   (nenhuma tool consulta a tabela `profile`), então isso teria que ser uma
   decisão de escopo antes de virar código: perguntar ao usuário se
   `"quem sou eu"` deveria cair em `fallback` (resposta genérica dizendo o
   que o Ceris faz) até que exista uma funcionalidade de perfil de verdade.
4. **Correção sugerida (sem inventar escopo novo):** adicione 1-2 exemplos
   de few-shot em `ROTEADOR_SHOT_N` dentro de `prompt_roteador.py` mostrando
   perguntas sobre identidade/perfil pessoal sendo classificadas como
   `fallback`, e garanta que `ORQUESTRADOR_PROMPT` (`prompt_orquestrador.py`)
   tem um exemplo de resposta de fallback que deixe claro que o Ceris não
   guarda/expõe dados de perfil ainda.

---

## HIPÓTESE 3 — Confiabilidade de function-calling do `openai/gpt-oss-20b`

1. `specialist_llm` (usado por `receitas`, `estoque`, `eventos`) é
   `gemini_llm.with_fallbacks([groq_llm])`, e `groq_llm`/`fast_llm` agora
   usam `openai/gpt-oss-20b`. Modelos menores/open-weight costumam ser
   menos confiáveis chamando tools corretamente do que os anteriores.
2. Teste isolado: force uma chamada usando só `gemini_llm` (comente
   temporariamente o `.with_fallbacks([groq_llm])`, sem apagar a linha,
   só pra teste) e repita as mesmas perguntas que falharam. Se o
   comportamento melhorar nitidamente, o problema é de confiabilidade do
   modelo de fallback, não de lógica do seu código.
3. Não decida sozinho por trocar de modelo de novo — é uma decisão de
   custo/desempenho que depende do resultado desse teste. Reporte o que
   observou antes de agir.

---

## HIPÓTESE 4 — Sessão/histórico não está sendo reaproveitada

1. Confirme no cliente (o que está chamando a API — Postman, front, etc.)
   se o `session_id` retornado pela primeira resposta está sendo reenviado
   nas mensagens seguintes da mesma conversa.
2. Se `session_id` estiver sempre `null`/vazio, `executar_chat` em
   `flow.py` cria uma sessão nova a cada mensagem
   (`ConversationsRepository.create_session`), e o agente nunca vê
   histórico — isso por si só explicaria respostas "desconexas" entre
   turnos, mesmo sem nenhum bug de código.

---

## HIPÓTESE 5 — `.env`/config centralizados não carregaram em algum módulo

1. Rode o serviço do zero (`uvicorn app.controller.config:app` ou como
   vocês sobem normalmente) e confira no log de inicialização se algum
   `ValueError`/`None` aparece relacionado a `MONGODB_URI`, `PGSQL_URL`,
   `GEMINI_API_KEY`, `GROQ_API_KEY`, `QDRANT_DATABASE_URL`.
2. Se algo vier `None`, o problema é ordem de import: `app/config.py`
   precisa ser importado (mesmo que indiretamente) antes de qualquer
   módulo que use essas constantes. Verifique se não sobrou nenhuma
   chamada antiga a `os.getenv`/`load_dotenv` fora de `app/config.py` (a
   busca é: `grep -rn "os.getenv\|load_dotenv" app/` e qualquer ocorrência
   fora de `app/config.py` é suspeita).

---

## ORDEM DE EXECUÇÃO

Teste a Hipótese 1 primeiro — é a mais provável de explicar exatamente o
sintoma "fica pedindo meus produtos" (que já deveriam estar disponíveis via
`get_stock`). Só passe para a próxima hipótese depois de confirmar ou
descartar a anterior com evidência (log/print), não por suposição.

Ao final, reporte um resumo de qual(is) hipótese(s) foram confirmadas, o
que foi corrigido, e o que ainda ficou pendente de decisão (ex.: escopo de
"quem sou eu", troca de modelo).