---
name: Montar lista de compras
description: Cria uma lista de compras, a partir de uma receita da conversa ou salva, das receitas de um evento, do que falta no estoque, ou de itens que a pessoa dita. Use quando ela quer uma lista nova.
metadata:
  dominio: events
  rota: eventos
  intencao: Criar lista de compras
  ferramentas: [ingredientes_para_comprar, create_list, get_list, get_stock, get_missing_products, get_events, buscar_receitas_usuario, somar_valores, calcular_percentual]
  version: 1.0.0
---

# Montar lista de compras

## Quando assumir esta skill

A pessoa quer uma lista de compras nova: do zero, a partir do que falta no
estoque, ou a partir das receitas de um evento.

Se a lista já existe e ela quer ver ou alterar, use `lista-gerenciar`.

## Fluxo

1. Leia a conversa antes de perguntar. “Dessa receita” significa a última receita apresentada: use seus ingredientes e quantidades, sem sugerir um prato novo. Para uma receita salva que não esteja no histórico, use `buscar_receitas_usuario` com o título.
2. Para evento, `get_events` e suas receitas JÁ vinculadas; nunca regenere cardápio ao montar a lista. Para reposição, `get_missing_products`. Para receita, `get_stock` para conferir o que há. Não invente quantidades faltantes nem subtraia pacotes de gramas: sem unidade comparável, inclua o ingrediente para conferência e avise que a quantidade disponível não pôde ser confirmada.
3. Para receita, chame `ingredientes_para_comprar` com TODOS os ingredientes e quantidades. Use `itens_para_comprar` como base de `create_list`, sem refazer contas. Para eventos, confira os ingredientes das receitas vinculadas da mesma forma. Onde a comparação não foi possível, avise que a quantidade precisa ser conferida. Só então `create_list` com o título e os itens.
4. `somar_valores` se a pessoa pedir o custo estimado.

## Regras

- Item que já está no estoque em quantidade suficiente **não entra na lista**.
  Comprar o que já se tem é o desperdício que o Ceris combate.
- Nunca peça `list_id` nem `event_id`. Resolva por `get_list` e `get_events`,
  casando pelo título ou pela data que a pessoa mencionou.
- Lista criada a partir de evento leva o nome do evento, para ela reconhecer
  depois.
- Pedido explícito com itens definidos (“crie a lista dessa receita”) já autoriza criar. Se você propôs uma lista e a pessoa confirmou, crie sem perguntar novamente. Pergunte só quando faltar receita, item, quantidade ou quando houver ambiguidade.
- Para receita avulsa, não crie evento e deixe `event_id` vazio. Não salve a receita sem pedido separado.
- `create_list` recebe título e itens com `name`, `quantity` numérica, `unitOfMeasure` e `checked: false`. Use as quantidades da receita. O retorno traz `_id` e `array_list`: repasse o que foi realmente criado.
- Se todos os itens já estiverem disponíveis em quantidade confirmada, diga que não falta comprar; não crie lista vazia.
- Falha de consulta ou gravação não é sucesso nem ausência de itens.

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

(get_events -> [{"id": "e1", "titulo": "Churrasco", "data": "2026-10-10", "qtd_pessoas": 10}])
(get_events -> receitas vinculadas com Picanha 4kg e Linguiça 2kg em falta)
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
