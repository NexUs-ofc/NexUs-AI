---
name: Criar evento com receita e compras
description: Cria em uma solicitação um evento novo, salva a receita já escolhida e monta uma lista de compras vinculada ao evento.
metadata:
  dominio: events
  rota: eventos
  intencao: Criar evento, salvar receita e montar lista
  ferramentas: [resolver_data, create_event, add_recipe, create_list]
  version: 1.0.0
---

# Criar evento com receita e compras

## Quando assumir esta skill

Use quando a pessoa pedir, na mesma mensagem, um evento novo, para salvar uma
receita já escolhida e para montar a lista de compras dessa receita/evento.
Preserve a receita a que “esse prato/essa receita” se refere no histórico; não
gere outro prato para simplificar o pedido.

## Preparação antes de qualquer gravação

1. Receba a receita e o identificador confirmados pelo agente de receitas em
   `RECEITA_SALVA_E_CONFIRMADA_PELO_AGENTE_DE_RECEITAS`. Se esse contexto não
   existir, pare e peça a receita. Não crie evento nem lista sem uma receita
   completa e salva confirmada.
2. Resolva referências como “amanhã” e “às 14h” com `resolver_data`, passando
   a referência e a hora. Não calcule datas de cabeça.
3. Reúna todos os dados obrigatórios do evento: título, descrição/tipo, data e
   hora, duração, local e número de pessoas. Use apenas dados declarados ou
   claramente presentes na receita/contexto. Se faltar duração ou outro campo,
   faça uma pergunta curta e específica antes de qualquer gravação. Não crie
   apenas parte do pedido enquanto espera a resposta. `create_event` recebe a
   duração em minutos inteiros: converta unidades explicitamente (por exemplo,
   “2 horas” = 120 minutos), sem confundir horário de início com duração.
4. A pessoa já autorizou explicitamente as três ações quando pediu para salvar
   a receita, criar a lista e marcar o evento. Não peça uma segunda confirmação
   depois de preencher os dados faltantes.

## Execução sequencial

Quando todos os dados estiverem disponíveis:

1. O agente de receitas já verificou se havia uma cópia salva e confirmou o ID
   da receita a usar; não repita essa tarefa nem crie outra cópia.
2. Chame `create_event` com os dados resolvidos. A data/hora precisa vir de
   `resolver_data`; nunca invente duração.
3. Use o id retornado por `create_event` e o id da receita confirmada para chamar
   `add_recipe`. Isso vincula a receita ao evento e escala ingredientes para o
   número de pessoas do evento.
4. Só após confirmar a receita vinculada, chame `create_list` com o id do
   evento. A ferramenta calcula os ingredientes faltantes pelo estoque atual e
   cria uma lista vinculada ao evento. Não inclua o que já existe em quantidade
   suficiente. Se não faltar nada, aceite o retorno `SEM_COMPRA` e não crie uma
   lista vazia.
5. Se alguma etapa falhar depois de outra gravação bem-sucedida, relate quais
   etapas foram confirmadas e qual falhou. Nunca diga que uma etapa foi concluída
   sem o retorno correspondente. Oriente a pessoa a conferir os registros antes
   de repetir uma etapa cujo resultado seja incerto.

## Saída

Retorne JSON com `dominio`, `intencao`, `resposta`, `evento`, `lista`,
`recomendacao` e `acompanhamento`. Use `esclarecer` se faltar um dado antes das
gravações. Inclua em `lista` somente os dados realmente retornados pela
ferramenta. Na resposta, informe separadamente o que foi criado/salvo e o que
não foi confirmado.
