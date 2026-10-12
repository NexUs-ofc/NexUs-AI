---
name: Gerenciar evento
description: Consulta, atualiza, adia ou cancela um evento que já existe. Use quando a pessoa pergunta sobre a agenda dela ou quer mexer num evento já criado.
metadata:
  dominio: events
  rota: eventos
  intencao: Consultar eventos | Atualizar evento | Cancelar evento
  ferramentas: [get_events, resolver_data, postpone_event, update_description, cancel_event]
  version: 1.0.0
---

# Gerenciar evento

## Quando assumir esta skill

A pessoa pergunta sobre a agenda ("tenho algo esse fim de semana?") ou quer
mexer num evento já criado: adiar, mudar descrição, cancelar.

Se o evento ainda não existe, use `evento-criar`. Se o assunto é receita do
evento, use `evento-receitas`.

## Fluxo

1. `resolver_data` quando ela falar em período por extenso ("essa semana",
   "sábado", "mês que vem"), para montar o filtro de datas.
2. `get_events` com o filtro. É também como você descobre o `event_id` —
   case pelo título ou pela data que ela mencionou.
3. A alteração conforme o pedido: `postpone_event` para adiar,
   `update_description` para mudar a descrição, `cancel_event` para cancelar.

## Regras

- Nunca peça `event_id`. Resolva por `get_events` e case pelo que ela
  descreveu.
- Se mais de um evento casar com a descrição, pergunte qual antes de alterar.
- **Cancelar exige confirmação explícita.** Consultar e adiar não exigem, mas
  adiar você confirma a data nova na resposta.
- Se não houver evento no período, diga que não há. Não invente nenhum, nem
  ofereça um evento parecido de outro período como se fosse o pedido.
- Data nova de adiamento sai de `resolver_data`, não da sua conta.

## Saída

- `intencao` : `"Consultar eventos"`, `"Atualizar evento"` ou
  `"Cancelar evento"`

```
evento: {
    titulo: "...",
    descricao: "...",
    data: "AAAA-MM-DD",
    inicio: "HH:MM",
    duracao: X,
    fim: "HH:MM",
    local: "...",
    qtd_pessoas: X
}
```

## Exemplos

```
Entrada:
ROUTE=events
PERGUNTA_ORIGINAL=Quais eventos eu tenho essa semana?
HOUSEHOLD_ID=1

(resolver_data(referencia="hoje") -> {"data": "2026-10-05", "dia_semana": "segunda-feira"})
(get_events(household_id=1, inicio="2026-10-05", fim="2026-10-11") -> [])

Resposta:
{
    "dominio": "events",
    "intencao": "Consultar eventos",
    "resposta": "Você não tem nenhum evento marcado para esta semana.",
    "recomendacao": ""
}
```

```
Entrada:
ROUTE=events
PERGUNTA_ORIGINAL=Adia o churrasco pro domingo.
HOUSEHOLD_ID=1

(get_events -> [{"id": "e1", "titulo": "Churrasco", "data": "2026-10-10"}])
(resolver_data(referencia="domingo") -> {"data": "2026-10-11", "dia_semana": "domingo"})
(postpone_event -> ok)

Resposta:
{
    "dominio": "events",
    "intencao": "Atualizar evento",
    "resposta": "Churrasco adiado para domingo, 11/10/2026.",
    "recomendacao": "",
    "acompanhamento": "A lista de compras continua a mesma."
}
```
