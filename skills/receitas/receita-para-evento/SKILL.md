---
name: Receita para evento
description: Recomenda pratos escalados para a quantidade de convidados de um evento. Use quando a entrada trouxer CHAMADO_POR=events, ou quando a pessoa pedir receita para um evento com número de pessoas.
metadata:
  dominio: receitas
  rota: receitas
  intencao: Recomendar receita para evento
  ferramentas: [consultar_preferencias, get_stock, escalar_quantidades, somar_valores, salvar_receita]
  version: 1.0.0
---

# Receita para evento

## Quando assumir esta skill

A entrada traz `CHAMADO_POR=events`, ou a pessoa pede receita para um evento
com quantidade de convidados.

## Fluxo

1. `consultar_preferencias`, para respeitar restrições dos anfitriões.
2. `get_stock`, para saber o que já existe e não precisa ser comprado.
3. Escolha pratos adequados ao tipo do evento: churrasco pede carne e
   acompanhamento, aniversário pede doce e salgado, jantar pede prato único.
4. `escalar_quantidades` em cada receita, da porção base para o total de
   pessoas.
5. `somar_valores` se precisar totalizar quantidades entre receitas.

## Regras

- Quando `CHAMADO_POR=events`, quem lê é o agente de eventos, não a pessoa.
  **Não faça pergunta de clarificação nesse caso** — responda com o que tem.
  Perguntar ali é perguntar no vazio.
- Toda quantidade sai escalada para o total de pessoas. Porção individual aqui
  é erro.
- `ingredientes_faltantes` é o que vai virar lista de compras. Um ingrediente
  esquecido aqui é um item que falta na festa.
- Não invente a quantidade de pessoas. Se ela não veio e não dá para deduzir,
  peça em `esclarecer` — e só então.

## Saída

- `intencao` : `"Recomendar receita para evento"`
- `receita` : o objeto abaixo

```
receita: {
    titulo: "...",
    porcoes: X,
    ingredientes: [
        {ingrediente: "...", quantidade_total: "Xkg", tem_suficiente: true}
    ],
    instrucoes: ["...", "..."],
    ingredientes_faltantes: ["..."],
    tempo_estimado: "...",
    dificuldade: "..."
}
```

- `porcoes` é o total de convidados, não a porção base da receita.
- `quantidade_total` é a quantidade já escalada para `porcoes`.
- `ingredientes_faltantes` lista os nomes com `tem_suficiente: false`.

## Exemplo

```
Entrada:
ROUTE=receitas
PERGUNTA_ORIGINAL=Churrasco para 10 pessoas, preciso de sugestões.
PROFILE_ID=7
ACCOUNT_ID=7
CHAMADO_POR=events

(get_stock -> [{"food_name": "Carvão", "quantity": 2}])
(escalar_quantidades -> {"fator": 10.0, "quantidades": [4000.0, 2000.0]})

Resposta:
{
    "dominio": "receitas",
    "intencao": "Recomendar receita para evento",
    "resposta": "Para 10 pessoas, 4kg de picanha e 2kg de linguiça dão conta do churrasco.",
    "recomendacao": "O carvão você já tem; falta a carne.",
    "receita": {
        "titulo": "Churrasco para 10",
        "porcoes": 10,
        "ingredientes": [
            {"ingrediente": "Picanha", "quantidade_total": "4kg", "tem_suficiente": false},
            {"ingrediente": "Linguiça", "quantidade_total": "2kg", "tem_suficiente": false},
            {"ingrediente": "Carvão", "quantidade_total": "2 sacos", "tem_suficiente": true}
        ],
        "instrucoes": ["Tempere a carne com antecedência.", "Acenda o carvão 40 minutos antes."],
        "ingredientes_faltantes": ["Picanha", "Linguiça"],
        "tempo_estimado": "3 horas",
        "dificuldade": "média"
    }
}
```
