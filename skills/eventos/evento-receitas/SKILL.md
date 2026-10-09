---
name: Receitas do evento
description: Monta o cardápio de um evento - sugere, adiciona e remove receitas ligadas a ele. Use quando a pessoa fala do que vai servir num evento que já existe.
metadata:
  dominio: events
  rota: eventos
  intencao: Adicionar receita ao evento | Remover receita ao evento
  ferramentas: [get_events, recomendar_receita, add_recipe, remove_recipe]
  version: 1.0.0
---

# Receitas do evento

## Quando assumir esta skill

A pessoa fala do que vai servir num evento que já existe: pedir sugestão de
cardápio, acrescentar um prato, tirar um prato.

Se ela quer a lista de compras, use `lista-montar`. Se quer criar o evento,
use `evento-criar`.

## Fluxo

1. `get_events` para achar o evento e descobrir `qtd_pessoas`. Case pelo
   título ou pela data.
2. `recomendar_receita` para as sugestões. Passe o tipo do evento e a
   quantidade de pessoas — é isso que faz as quantidades saírem escaladas.
3. `add_recipe` ou `remove_recipe` conforme o pedido, depois de confirmado.

## Regras

- `recomendar_receita` devolve as quantidades já escaladas para o total de
  pessoas. Repasse como vieram; não recalcule.
- Nunca peça `event_id` nem `recipe_id`. Resolva por `get_events` e case pelo
  título.
- Acrescentar ou remover prato só depois de confirmado pela pessoa.
- Se o evento não tiver quantidade de pessoas registrada, pergunte antes de
  sugerir — sem ela a quantidade de cada prato é chute.
- Depois de montar o cardápio, ofereça montar a lista de compras. Uma vez.

## Saída

- `intencao` : `"Adicionar receita ao evento"` ou
  `"Remover receita ao evento"`

Quando incluir `evento`, as receitas entram assim:

```
evento: {
    titulo: "...",
    data: "AAAA-MM-DD",
    qtd_pessoas: X,
    receitas: [
        {
            id_receita: "...",
            titulo: "...",
            ingredientes: [
                {ingrediente: "...", quantidade_total: "Xkg", tem_suficiente: true}
            ]
        }
    ]
}
```

## Exemplo

```
Entrada:
ROUTE=events
PERGUNTA_ORIGINAL=Adiciona pão de alho no churrasco.
HOUSEHOLD_ID=1
ACCOUNT_ID=1

(get_events -> [{"id": "e1", "titulo": "Churrasco", "data": "2026-10-10", "qtd_pessoas": 10}])
(recomendar_receita -> {"titulo": "Pão de alho", "ingredientes": [
    {"ingrediente": "Pão de alho", "quantidade_total": "20 unidades", "tem_suficiente": false}]})
(add_recipe -> ok)

Resposta:
{
    "dominio": "events",
    "intencao": "Adicionar receita ao evento",
    "resposta": "Adicionei pão de alho ao churrasco: 20 unidades para as 10 pessoas.",
    "recomendacao": "",
    "acompanhamento": "Quer que eu inclua na lista de compras?"
}
```
