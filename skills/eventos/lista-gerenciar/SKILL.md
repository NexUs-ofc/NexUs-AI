---
name: Gerenciar lista de compras
description: Mostra, altera e acompanha uma lista que já existe - consultar, adicionar ou tirar item, marcar como comprado, renomear. Use quando a lista já foi criada.
metadata:
  dominio: events
  rota: eventos
  intencao: Consultar lista de compras | Atualizar lista de compras
  ferramentas: [get_list, renomear_lista, alterar_item_lista, calcular_percentual, somar_valores]
  version: 1.0.0
---

# Gerenciar lista de compras

## Quando assumir esta skill

A pessoa quer ver, alterar ou acompanhar uma lista que já existe: consultar,
acrescentar ou tirar item, marcar como comprado, renomear.

Se ela quer uma lista nova, use `lista-montar`.

## Fluxo

1. `get_list(title="nome citado")` para carregar a lista; sem título, consulte as recentes. Use o `_id` retornado, nunca pergunte id à pessoa.
2. Se houver mais de uma lista com nome parecido, pergunte qual antes de
   alterar qualquer coisa.
3. Para renomear: `renomear_lista` com `title`. Para itens: `alterar_item_lista` com o id do item e a operação `quantidade`, `comprado`, `adicionar` ou `remover`. Envie somente os campos da operação atual. Nunca substitua a lista completa para editar um item.
4. `calcular_percentual` para o progresso, sempre que for mencioná-lo.

## Regras

- Nunca peça `list_id`. Resolva por `get_list` e case pelo título.
- Um pedido explícito e sem ambiguidade já autoriza a alteração (“marca o arroz como comprado”). Não repita uma confirmação recebida. Pergunte somente se não souber qual lista ou item alterar.
- Marcar item como comprado **não o remove** da lista: ele continua lá,
  marcado.
- Não retome pedidos antigos que falharam. Alterar a quantidade não autoriza marcar comprado, e vice-versa.
- Listas com títulos iguais: diferencie por data, evento e itens; peça uma escolha humana antes de alterar. Não exponha identificadores internos.
- Ao terminar a lista inteira, diga que ela está completa e oriente a inclusão
  dos produtos pelas telas do aplicativo. Nunca ofereça lançá-los pelo chat.
- Retorno `[]` significa nenhuma lista encontrada. Retorno `FALHA` significa consulta indisponível; não diga que a lista não existe.
- O contrato dos itens usa `name`, `quantity`, `unitOfMeasure`, `checked` e `id`; preserve id e estado dos itens que não mudaram.

## Saída

- `intencao` : `"Consultar lista de compras"` ou `"Atualizar lista de compras"`

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

- `progresso` sai de `calcular_percentual`. Nunca calcule de cabeça.
- `comprado` reflete o que a pessoa marcou, não o que você supõe.

## Exemplos

```
Entrada:
ROUTE=events
PERGUNTA_ORIGINAL=Já comprei a picanha, marca lá.

(get_list -> {"id": "l1", "titulo": "Churrasco", "itens": [
    {"nome": "Picanha", "comprado": false}, {"nome": "Linguiça", "comprado": false}]})
(alterar_item_lista -> ok)
(calcular_percentual -> {"percentual": 50, "parte": 1, "total": 2})

Resposta:
{
    "dominio": "events",
    "intencao": "Atualizar lista de compras",
    "resposta": "Marquei a picanha como comprada. A lista do churrasco está em 50%.",
    "recomendacao": "",
    "acompanhamento": "Falta a linguiça."
}
```

```
Entrada:
ROUTE=events
PERGUNTA_ORIGINAL=Como está a lista do churrasco?

(get_list -> {"id": "l1", "titulo": "Churrasco", "itens": [
    {"nome": "Picanha", "comprado": true}, {"nome": "Linguiça", "comprado": true}]})
(calcular_percentual -> {"percentual": 100, "parte": 2, "total": 2})

Resposta:
{
    "dominio": "events",
    "intencao": "Consultar lista de compras",
    "resposta": "A lista do churrasco está completa: picanha e linguiça já foram compradas.",
    "recomendacao": "",
    "acompanhamento": "Para incluir as compras no estoque, use a tela de estoque, o leitor de código de barras ou a foto da nota fiscal no aplicativo."
}
```
