---
name: Consultar estoque
description: Responde o que a pessoa tem em casa, em que quantidade. Use para perguntas de consulta, sem alteração.
metadata:
  dominio: stock
  rota: estoque
  intencao: Listar estoque para usuário
  ferramentas: [get_stock, get_foods, somar_valores, calcular_percentual]
  version: 1.0.0
---

# Consultar estoque

## Quando assumir esta skill

A pessoa quer saber o que tem em casa: "tenho arroz?", "o que tem no meu
estoque?", "quantos ovos eu tenho?".

Se a pergunta é sobre validade, use `estoque-validade`. Se é sobre o que
comprar, use `estoque-compras`.

## Fluxo

1. `get_stock` para o estoque completo.
2. Filtre pelo que ela perguntou. Se foi item específico, responda sobre ele;
   se foi geral, resuma.
3. `somar_valores` ou `calcular_percentual` se a resposta envolver total ou
   proporção. Nunca some de cabeça.

## Regras

- **Responda, não pergunte.** Esta é uma consulta: a informação está toda no
  `get_stock`. Pergunta aqui é quase sempre desnecessária.
- Estoque vazio é resposta: diga que está vazio e ofereça registrar. Não
  invente item nenhum.
- Item que a pessoa perguntou e não existe: diga que não tem. Não ofereça um
  parecido como se fosse o pedido.
- Em lista longa, agrupe e resuma em vez de recitar item por item.
- Não repita `food_id` nem `pantry_item_id` na resposta.

## Saída

- `intencao` : `"Listar estoque para usuário"`

## Exemplos

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Tenho arroz em casa?
PROFILE_ID=1

(get_stock -> [{"food_name": "Arroz", "quantity": 3, "expiry_date": "2027-02-01"}])

Resposta:
{
    "dominio": "stock",
    "intencao": "Listar estoque para usuário",
    "resposta": "Sim, você tem 3 unidades de arroz.",
    "recomendacao": ""
}
```

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=O que eu tenho no estoque?
PROFILE_ID=1

(get_stock -> "O usuário não possui nenhum produto cadastrado no estoque.")

Resposta:
{
    "dominio": "stock",
    "intencao": "Listar estoque para usuário",
    "resposta": "Seu estoque está vazio.",
    "recomendacao": "",
    "acompanhamento": "Quer registrar o que você tem em casa?"
}
```
