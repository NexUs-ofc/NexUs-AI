---
name: Gerenciar lista de compras
description: Mostra, altera e acompanha uma lista que já existe - consultar, adicionar ou tirar item, marcar como comprado, renomear. Use quando a lista já foi criada.
metadata:
  dominio: events
  rota: eventos
  intencao: Consultar lista de compras | Atualizar lista de compras
  ferramentas: [get_list, update_list, calcular_percentual, somar_valores]
  version: 1.0.0
---

# Gerenciar lista de compras

## Quando assumir esta skill

A pessoa quer ver, alterar ou acompanhar uma lista que já existe: consultar,
acrescentar ou tirar item, marcar como comprado, renomear.

Se ela quer uma lista nova, use `lista-montar`.

## Fluxo

1. `get_list` para carregar a lista. Case pelo título que a pessoa usou.
2. Se houver mais de uma lista com nome parecido, pergunte qual antes de
   alterar qualquer coisa.
3. `update_list` com a alteração pedida.
4. `calcular_percentual` para o progresso, sempre que for mencioná-lo.

## Regras

- Nunca peça `list_id`. Resolva por `get_list` e case pelo título.
- Alteração só depois de confirmada pela pessoa. Consulta não precisa de
  confirmação.
- Marcar item como comprado **não o remove** da lista: ele continua lá,
  marcado.
- Ao terminar a lista inteira, diga que ela está completa e ofereça lançar os
  itens no estoque — é a ponte entre comprar e guardar.
- Se a lista não existir, diga isso e ofereça criar. Não invente conteúdo.

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
HOUSEHOLD_ID=1
ACCOUNT_ID=1

(get_list -> {"id": "l1", "titulo": "Churrasco", "itens": [
    {"nome": "Picanha", "comprado": false}, {"nome": "Linguiça", "comprado": false}]})
(update_list -> ok)
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
HOUSEHOLD_ID=1
ACCOUNT_ID=1

(get_list -> {"id": "l1", "titulo": "Churrasco", "itens": [
    {"nome": "Picanha", "comprado": true}, {"nome": "Linguiça", "comprado": true}]})
(calcular_percentual -> {"percentual": 100, "parte": 2, "total": 2})

Resposta:
{
    "dominio": "events",
    "intencao": "Consultar lista de compras",
    "resposta": "A lista do churrasco está completa: picanha e linguiça já foram compradas.",
    "recomendacao": "",
    "acompanhamento": "Quer que eu lance esses itens no seu estoque?"
}
```
