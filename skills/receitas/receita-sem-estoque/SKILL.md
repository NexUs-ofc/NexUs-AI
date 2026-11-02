---
name: Receita sem usar estoque
description: Gera uma receita independente do inventário quando a pessoa pede explicitamente para não considerar o estoque.
metadata:
  dominio: receitas
  rota: receitas
  intencao: Sugerir receita
  ferramentas: []
  version: 1.0.0
---

# Receita sem usar o estoque

## Quando assumir esta skill

Use somente quando a pessoa pedir explicitamente uma receita sem usar,
considerar ou aproveitar o que tem no estoque.

## Regras

- Este pedido substitui a preferência padrão de consultar o estoque. Não chame
  ferramentas de estoque nem compare ingredientes com o inventário.
- Sugira uma receita culinariamente coerente e completa, com ingredientes,
  quantidades e passos suficientes para prepará-la.
- Não afirme que qualquer ingrediente está ou não está no estoque. Não marque
  ingredientes como disponíveis, faltantes ou para comprar; a pessoa pediu uma
  receita independente do inventário.
- Preserve o prato ou ingrediente que a pessoa pediu, se houver. Se o pedido for
  aberto, escolha uma receita conhecida e equilibrada, sem inventar combinações.
- Respeite restrições alimentares explícitas na mensagem e as restrições do
  perfil fornecidas na entrada.
- Não reutilize uma receita anterior, a menos que a pessoa a referencie
  explicitamente.

## Saída

Retorne JSON com `dominio`, `intencao`, `resposta` e `receita`. Em `receita`,
inclua `titulo`, `porcoes`, `ingredientes` com `ingrediente` e
`quantidade_total`, `instrucoes`, `tempo_preparo_minutos` e `dificuldade`.
Não inclua campos de disponibilidade ou compra.
