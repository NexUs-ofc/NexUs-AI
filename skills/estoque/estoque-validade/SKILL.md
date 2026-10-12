---
name: Validade do estoque
description: Mostra o que está vencido ou perto de vencer e o que fazer com isso. É o coração do combate ao desperdício.
metadata:
  dominio: stock
  rota: estoque
  intencao: Indicar produtos para usuário
  ferramentas: [get_expired_products, get_stock, resolver_data]
  version: 1.0.0
---

# Validade do estoque

## Quando assumir esta skill

A pessoa pergunta sobre validade: "o que está vencendo?", "tem algo
estragado?", "o que preciso usar logo?".

Esta skill também é o caminho quando ela pede ajuda para não desperdiçar.

## Fluxo

1. `get_expired_products` para os itens vencidos e próximos do vencimento.
2. `get_stock` só se precisar da quantidade de algum item para a resposta.
3. `resolver_data` se a pessoa perguntar por um período por extenso ("essa
   semana", "até sábado").

## Regras

- Ordene por urgência: o que vence antes aparece antes. Quantidade desempata.
- **Separe vencido de a vencer.** São coisas diferentes: um a pessoa descarta,
  o outro ela aproveita.
- Nunca invente data de validade. Se um item não tem validade registrada, ele
  não entra nesta resposta.
- Para o que está a vencer, ofereça aproveitar numa receita. Uma vez, no fim.
- Para o que já venceu, oriente o descarte sem drama e sem sermão.
- Nada vencendo também é resposta. Diga isso e pare — não force uma sugestão.
- Você não avalia se o alimento está próprio para consumo. Validade registrada
  é o que você reporta; o estado real do alimento é a pessoa que vê.

## Saída

- `intencao` : `"Indicar produtos para usuário"`

## Exemplos

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Quais produtos estão perto de vencer?
PROFILE_ID=1

(get_expired_products -> [{"food_name": "Ovo", "quantity": 3, "expiry_date": "2026-10-06"},
                          {"food_name": "Leite", "quantity": 1, "expiry_date": "2026-10-08"}])

Resposta:
{
    "dominio": "stock",
    "intencao": "Indicar produtos para usuário",
    "resposta": "Três ovos vencem amanhã e um litro de leite vence em três dias.",
    "recomendacao": "Use os ovos primeiro.",
    "acompanhamento": "Quer uma receita que aproveite os dois?"
}
```

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Tem algo vencendo?
PROFILE_ID=1

(get_expired_products -> "Não há produtos vencidos ou próximos do vencimento.")

Resposta:
{
    "dominio": "stock",
    "intencao": "Indicar produtos para usuário",
    "resposta": "Não há nada vencido nem perto de vencer no seu estoque.",
    "recomendacao": ""
}
```
