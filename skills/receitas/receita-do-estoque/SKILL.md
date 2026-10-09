---
name: Receita do estoque
description: Sugere uma receita que cabe no estoque de hoje, priorizando o que vence primeiro. Use quando a pessoa pede sugestão a partir do que ela já tem em casa, ou pede para aproveitar o que está vencendo.
metadata:
  dominio: receitas
  rota: receitas
  intencao: Sugerir receita
  ferramentas: [consultar_preferencias, get_stock, get_expired_products, buscar_receitas_usuario, escalar_quantidades]
  version: 1.0.0
---

# Receita do estoque

## Quando assumir esta skill

A pessoa pede sugestão de receita a partir do que ela já tem em casa, ou pede
para aproveitar o que está vencendo.

Não assuma esta skill se houver restrição alimentar ou pedido de substituição
(use `receita-com-restricao`), nem se a entrada trouxer `CHAMADO_POR=events`
(use `receita-para-evento`).

## Fluxo

1. `consultar_preferencias`, para saber gostos e restrições registrados.
2. `get_stock`, para o estoque com a validade de cada item.
3. `get_expired_products`, para saber o que corre risco de vencer.
4. Escolha uma receita cujos ingredientes principais já estejam no estoque,
   com preferência pelos de validade mais curta.
5. `buscar_receitas_usuario` SOMENTE se a pessoa pedir algo diferente do que
   já foi sugerido antes.
6. `escalar_quantidades` para ajustar as quantidades. Não multiplique de
   cabeça.

## Regras

- A receita nasce do estoque, não do seu repertório. Se faltar ingrediente
  principal, diga o que falta em vez de fingir que tem.
- Ingrediente que a pessoa não tem entra em `ingredientes_faltantes`, nunca
  some da lista.
- Se o estoque estiver vazio, diga isso e ofereça montar a lista de compras.
  Não invente uma receita genérica.

## Saída

- `intencao` : `"Sugerir receita"`
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

- `quantidade_total` é a quantidade já escalada para `porcoes`, nunca a porção
  individual.
- `tem_suficiente` compara essa quantidade com o que `get_stock` devolveu.
- `ingredientes_faltantes` lista os nomes com `tem_suficiente: false`. Os dois
  campos têm que concordar entre si.

## Exemplo

```
Entrada:
ROUTE=receitas
PERGUNTA_ORIGINAL=Me sugere algo com o que está vencendo.
PROFILE_ID=7
ACCOUNT_ID=7

(consultar_preferencias -> {"restricoes": []})
(get_stock -> [{"food_name": "Tomate", "quantity": 4, "expiry_date": "2026-10-10"},
               {"food_name": "Macarrão", "quantity": 1, "expiry_date": "2027-01-10"}])

Resposta:
{
    "dominio": "receitas",
    "intencao": "Sugerir receita",
    "resposta": "Dá para fazer um macarrão ao sugo com os tomates que vencem em dois dias.",
    "recomendacao": "Use os quatro tomates nesta receita.",
    "receita": {
        "titulo": "Macarrão ao sugo",
        "porcoes": 2,
        "ingredientes": [
            {"ingrediente": "Tomate", "quantidade_total": "4 unidades", "tem_suficiente": true},
            {"ingrediente": "Macarrão", "quantidade_total": "1 pacote", "tem_suficiente": true}
        ],
        "instrucoes": ["Cozinhe o macarrão.", "Refogue os tomates picados e misture."],
        "ingredientes_faltantes": [],
        "tempo_estimado": "30 minutos",
        "dificuldade": "fácil"
    }
}
```
