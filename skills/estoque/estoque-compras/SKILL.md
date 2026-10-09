---
name: Sugestão de compras
description: Diz o que está em falta e o que vale comprar, a partir do mínimo configurado e dos hábitos de consumo. Use quando a pessoa pergunta o que precisa comprar.
metadata:
  dominio: stock
  rota: estoque
  intencao: Listar produtos para comprar
  ferramentas: [get_missing_products, get_category_info, get_brand_info, get_stock, somar_valores]
  version: 1.0.0
---

# Sugestão de compras

## Quando assumir esta skill

A pessoa pergunta o que precisa comprar: "o que está faltando?", "o que eu
preciso comprar?", "me sugere o que levar no mercado".

Para criar a lista propriamente dita, use `lista-montar`. Esta skill diz **o
quê**; aquela monta a lista.

## Fluxo

1. `get_missing_products` para o que está abaixo do mínimo. Essa é a base.
2. `get_category_info` e `get_brand_info` para entender o padrão de consumo —
   use só quando a pessoa pede sugestão, não quando ela só quer saber o que
   falta.
3. `get_stock` se precisar confirmar quantidade de algum item.
4. `somar_valores` se ela pedir estimativa de quanto vai gastar.

## Regras

- **Falta é falta; sugestão é sugestão.** Diga primeiro o que está abaixo do
  mínimo, e só depois o que você sugere pelos hábitos. Misturar os dois faz a
  pessoa comprar o que não precisa.
- Nunca sugira comprar algo que já está no estoque em quantidade suficiente.
- Sugestão por hábito sai dos relatórios, não do seu palpite. Se os relatórios
  vierem vazios, não sugira nada — diga só o que falta.
- Nada faltando também é resposta. Diga isso e pare.
- Não invente preço. Se ela pedir estimativa e você não tem os valores, diga
  que não tem.

## Saída

- `intencao` : `"Listar produtos para comprar"`

## Exemplo

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=O que eu preciso comprar?
PROFILE_ID=1

(get_missing_products -> [{"food_name": "Arroz", "quantity": 0, "minimum_quantity": 2},
                          {"food_name": "Leite", "quantity": 1, "minimum_quantity": 3}])
(get_category_info -> [{"categoria": "Hortifruti", "total_produtos": 8}])

Resposta:
{
    "dominio": "stock",
    "intencao": "Listar produtos para comprar",
    "resposta": "Faltam arroz, que acabou, e leite, que está em 1 de 3.",
    "recomendacao": "Hortifruti é o que você mais consome; vale repor junto.",
    "acompanhamento": "Quer que eu monte a lista de compras com esses itens?"
}
```
