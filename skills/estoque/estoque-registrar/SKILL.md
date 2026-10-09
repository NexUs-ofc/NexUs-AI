---
name: Registrar no estoque
description: Adiciona e remove produtos do estoque. Use quando a pessoa diz que comprou, consumiu, descartou ou acabou alguma coisa.
metadata:
  dominio: stock
  rota: estoque
  intencao: Adicionar produto ao estoque | Remover produto de estoque
  ferramentas: [resolver_alimento, resolver_data, add_product, remove_product, get_stock]
  version: 1.0.0
---

# Registrar no estoque

## Quando assumir esta skill

A pessoa diz que comprou, consumiu, descartou ou acabou alguma coisa:
"comprei 2 pacotes de arroz", "acabou o leite", "joguei fora o tomate".

Se ela quer refazer o estoque inteiro, use `estoque-atualizacao-guiada`.

## Fluxo

**Para adicionar:**

1. `resolver_alimento` com o nome que a pessoa falou. Ele devolve o `food_id`
   e **cadastra o alimento se ele não existir no catálogo**.
2. `resolver_data` se a validade vier por extenso ("semana que vem", "dia 20").
3. `add_product` com o `food_id` que voltou.

**Para remover:**

1. `get_stock` e encontre o item cujo `food_name` corresponde ao que a pessoa
   mencionou.
2. `remove_product` com o `pantry_item_id` desse item.

## Regras

- **Alimento fora do catálogo não é impedimento.** `resolver_alimento`
  cadastra. Nunca diga que o alimento não existe no sistema.
- Se `resolver_alimento` devolver `ambiguo`, pergunte qual das opções antes de
  seguir.
- Para adicionar você precisa de **exatamente três coisas** da pessoa: nome,
  quantidade e validade. **Nada além disso.** Não pergunte unidade de medida,
  marca, categoria, local de armazenamento nem preço — `add_product` não recebe
  esses dados, e perguntar só faz ela perder tempo.
- Nunca pergunte `food_id` nem `pantry_item_id`. Você resolve os dois sozinho.
- Se ela já deu nome, quantidade e validade, **execute**. Não peça confirmação
  de dado que ela acabou de informar.
- Mesmo alimento com a mesma validade soma na linha que já existe. Isso é
  automático; não avise sobre o detalhe.

## Saída

- `intencao` : `"Adicionar produto ao estoque"` ou
  `"Remover produto de estoque"`

## Exemplo

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Adiciona 2 pés de alface no meu estoque, validade 20/10/2026.
PROFILE_ID=1

(resolver_alimento(nome="alface") -> {"food_id": 145, "food_name": "alface", "criado": true})
(add_product(profile_id=1, food_id=145, quantity=2, expiry_date="20/10/2026") -> ok)

Resposta:
{
    "dominio": "stock",
    "intencao": "Adicionar produto ao estoque",
    "resposta": "Adicionei 2 pés de alface ao seu estoque, com validade em 20/10/2026.",
    "recomendacao": "",
    "acompanhamento": "Tem mais alguma coisa para registrar?"
}
```
