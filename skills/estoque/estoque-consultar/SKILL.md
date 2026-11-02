---
name: Consultar estoque
description: Responde o que a pessoa tem em casa, em que quantidade. Use para perguntas de consulta, sem alteração.
metadata:
  dominio: stock
  rota: estoque
  intencao: Listar estoque para usuário
  ferramentas: [get_stock, somar_valores, calcular_percentual]
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
- Estoque vazio é resposta: diga que está vazio. Não invente itens nem prometa
  cadastrar pelo chat.
- Item que a pessoa perguntou e não existe: diga que não tem. Não ofereça um
  parecido como se fosse o pedido.
- Consulte `get_stock` para afirmar saldo atual. O campo `quantity` é o número
  de embalagens/unidades cadastradas; `unit_of_measure` e `package_quantity`
  descrevem o conteúdo de cada embalagem. Respeite ambos ao informar a unidade:
  por exemplo, 3 embalagens de 500 g são “3 pacotes de 500 g”, não “3 g” nem
  “1.500 unidades”. Para `unit_of_measure="unit"`, use unidades; para `g`,
  `kg`, `ml` ou `l`, informe o conteúdo e a quantidade por embalagem.
- `get_stock` exclui registros com saldo zero ou negativo. Não invente nem
  informe “0 unidades” para um produto ausente do resultado; diga que ele não
  consta no estoque atual. Histórico de compras/transações é outra consulta:
  não use o estoque atual para negar ou apagar fatos históricos e não descarte
  ferramentas ou campos que possam ser necessários a perguntas de histórico.
- Em lista longa, agrupe e resuma em vez de recitar item por item.
- Não repita `food_id` nem `pantry_item_id` na resposta.

## Saída

- `intencao` : `"Listar estoque para usuário"`

## Exemplos

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Tenho arroz em casa?

(get_stock -> [{"food_name": "Arroz", "quantity": 3, "package_quantity": 1,
"unit_of_measure": "unit", "expiry_date": "2027-02-01"}])

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

(get_stock -> "O usuário não possui nenhum produto cadastrado no estoque.")

Resposta:
{
    "dominio": "stock",
    "intencao": "Listar estoque para usuário",
    "resposta": "Seu estoque está vazio.",
    "recomendacao": "",
    "acompanhamento": "Para incluir produtos, use a tela de estoque, o leitor de código de barras ou a foto da nota fiscal no aplicativo."
}
```
