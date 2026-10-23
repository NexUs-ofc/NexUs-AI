---
name: Registrar no estoque
description: Tira produtos do estoque. Use quando a pessoa diz que consumiu, descartou ou acabou alguma coisa, ou pede para adicionar um produto (o chat não adiciona).
metadata:
  dominio: stock
  rota: estoque
  intencao: Remover produto de estoque | Adicionar produto ao estoque
  ferramentas: [remove_product, get_stock]
  version: 1.1.0
---

# Registrar no estoque

## Quando assumir esta skill

A pessoa diz que consumiu, descartou ou acabou alguma coisa: "acabou o
leite", "joguei fora o tomate". Ou pede para adicionar um produto:
"comprei 2 pacotes de arroz", "adiciona alface no estoque".

Se ela quer revisar o estoque inteiro, use `estoque-atualizacao-guiada`.

## Fluxo

**Para remover:**

1. `get_stock` e encontre o item cujo `food_name` corresponde ao que a pessoa
   mencionou.
2. `remove_product` com o `pantry_item_id` desse item.

**Para adicionar:** a conversa não adiciona produto ao estoque. Diga isso em
uma frase, sem chamar ferramenta, e que o cadastro é feito pelo aplicativo.

## Regras

- **Nunca adicione produto ao estoque.** Citar um alimento, dizer que
  comprou ou pedir para adicionar não grava nada.
- Nunca pergunte `pantry_item_id`. Você o encontra pelo `get_stock`.
- Se nenhum item do estoque corresponder ao que ela citou, diga que não
  encontrou. Não remova outro parecido sem perguntar.
- **Só diga "tirei" depois de `remove_product` ter respondido nesta rodada.**
  Sem a chamada, nada foi gravado.

## Saída

- `intencao` : `"Remover produto de estoque"` ou
  `"Adicionar produto ao estoque"` (quando só explicou que o chat não adiciona)

## Exemplos

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Acabou o leite.

(get_stock -> [{"pantry_item_id": 31, "food_name": "Leite", "quantity": 1}])
(remove_product(pantry_item_id=31) -> ok)

Resposta:
{
    "dominio": "stock",
    "intencao": "Remover produto de estoque",
    "resposta": "Tirei o leite do seu estoque.",
    "recomendacao": ""
}
```

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Comprei 2 pés de alface.

Resposta:
{
    "dominio": "stock",
    "intencao": "Adicionar produto ao estoque",
    "resposta": "Por aqui eu não adiciono produtos ao estoque; o cadastro é feito pelo aplicativo.",
    "recomendacao": ""
}
```
