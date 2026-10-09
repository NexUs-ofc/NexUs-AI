---
name: Montar lista de compras
description: Cria uma lista de compras, a partir das receitas de um evento, do que falta no estoque, ou de itens que a pessoa dita. Use quando ela quer uma lista nova.
metadata:
  dominio: events
  rota: eventos
  intencao: Criar lista de compras
  ferramentas: [create_list, get_list, get_missing_products, get_events, recomendar_receita, somar_valores]
  version: 1.0.0
---

# Montar lista de compras

## Quando assumir esta skill

A pessoa quer uma lista de compras nova: do zero, a partir do que falta no
estoque, ou a partir das receitas de um evento.

Se a lista já existe e ela quer ver ou alterar, use `lista-gerenciar`.

## Fluxo

1. Descubra a origem pela pergunta. Na dúvida entre evento e estoque,
   pergunte — é a única pergunta que vale fazer aqui.
2. Reúna os itens da origem escolhida.
3. `create_list` com o título e os itens.
4. `somar_valores` se a pessoa pedir o custo estimado.

## Regras

- Item que já está no estoque em quantidade suficiente **não entra na lista**.
  Comprar o que já se tem é o desperdício que o Ceris combate.
- Nunca peça `list_id` nem `event_id`. Resolva por `get_list` e `get_events`,
  casando pelo título ou pela data que a pessoa mencionou.
- Lista criada a partir de evento leva o nome do evento, para ela reconhecer
  depois.
- Confirme antes de criar, e diga quantos itens a lista terá.

## Saída

- `intencao` : `"Criar lista de compras"`

```
lista: {
    id: "...",
    titulo: "...",
    itens: [
        {nome: "...", quantidade: "Xkg", comprado: false}
    ],
    total_itens: X,
    comprados: X,
    progresso: X
}
```

- `progresso` é `comprados` sobre `total_itens` em porcentagem, e sai de
  `calcular_percentual`. Nunca calcule de cabeça.

## Exemplo

```
Entrada:
ROUTE=events
PERGUNTA_ORIGINAL=Monta a lista de compras do churrasco de sábado.
HOUSEHOLD_ID=1
PROFILE_ID=1
ACCOUNT_ID=1

(get_events -> [{"id": "e1", "titulo": "Churrasco", "data": "2026-10-10", "qtd_pessoas": 10}])
(recomendar_receita -> {"ingredientes_faltantes": ["Picanha", "Linguiça"]})
(create_list -> {"id": "l1", "titulo": "Churrasco"})

Resposta:
{
    "dominio": "events",
    "intencao": "Criar lista de compras",
    "resposta": "Criei a lista do churrasco com dois itens: picanha e linguiça.",
    "recomendacao": "O carvão já está no seu estoque, então ficou de fora.",
    "lista": {
        "id": "l1",
        "titulo": "Churrasco",
        "itens": [
            {"nome": "Picanha", "quantidade": "4kg", "comprado": false},
            {"nome": "Linguiça", "quantidade": "2kg", "comprado": false}
        ],
        "total_itens": 2,
        "comprados": 0,
        "progresso": 0
    }
}
```
