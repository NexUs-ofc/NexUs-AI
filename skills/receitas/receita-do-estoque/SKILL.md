---
name: Receita do estoque
description: Sugere uma receita que cabe no estoque de hoje, priorizando o que vence primeiro. Use quando a pessoa pede sugestão a partir do que ela já tem em casa, ou pede para aproveitar o que está vencendo.
metadata:
  dominio: receitas
  rota: receitas
  intencao: Sugerir receita
  ferramentas: [consultar_preferencias, get_stock, buscar_receitas_usuario, escalar_quantidades]
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

1. As preferências já vêm na linha PREFERENCIAS da entrada. Comece direto por
   `get_stock` — não gaste uma rodada pedindo o que já está na sua frente.
2. `get_stock` já traz a validade de cada item, e você tem a data de hoje no
   contexto. O que está vencido ou vencendo sai dessa lista por comparação —
   não existe ferramenta a chamar para isso.
3. Escolha uma receita cujos ingredientes principais já estejam no estoque,
   com preferência pelos de validade mais curta.
4. `buscar_receitas_usuario` SOMENTE se a pessoa pedir algo diferente do que
   já foi sugerido antes.
5. `escalar_quantidades` para ajustar as quantidades. Não multiplique de
   cabeça.

## Regras

- **Prioridade, não exclusão:** use primeiro o de validade mais curta que
  ainda não venceu, mas o resto do estoque continua disponível e entra quando
  a receita pede. Não faça prato pobre só para gastar o que vence antes.
- **PREFERENCIAS escolhe o prato**, validade só ordena dentro do que é
  compatível. Restrição alimentar nunca cede para aproveitar validade.
- **Vencido não entra na receita** (compare `expiry_date` com a data de hoje),
  nem nos ingredientes nem nas `instrucoes`. Cite uma vez no fim, para
  descarte.
- Se o não vencido não dá prato, diga o que dá, avise do vencido e ofereça a
  lista de compras.
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
- Peso, volume e medida de cozinha ("200 ml", "400 g", "½ xícara") existem
  SOMENTE dentro de `receita`. Em `resposta` e `recomendacao` cite o
  ingrediente pelo nome, sem quantidade: o estoque conta unidades e não pesos,
  então medida nesses campos é número sem origem.

## Exemplo

```
Entrada:
ROUTE=receitas
PERGUNTA_ORIGINAL=Me sugere algo com o que está vencendo.

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
