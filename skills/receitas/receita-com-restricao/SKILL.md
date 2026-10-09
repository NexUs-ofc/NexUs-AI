---
name: Receita com restrição
description: Adapta a receita à restrição alimentar da pessoa ou troca um ingrediente que ela pediu para substituir. Use quando houver alergia, dieta, intolerância, ou pedido explícito de troca de ingrediente.
metadata:
  dominio: receitas
  rota: receitas
  intencao: Sugerir receita | Substituir ingrediente
  ferramentas: [consultar_preferencias, get_stock, buscar_historico, tavily_search, escalar_quantidades]
  version: 1.0.0
---

# Receita com restrição

## Quando assumir esta skill

A pessoa tem restrição alimentar, alergia ou dieta, ou pede para trocar um
ingrediente específico da receita.

A restrição registrada em `consultar_preferencias` vale mesmo que a pessoa não
a repita no pedido — se existir restrição no perfil, esta skill se aplica.

## Fluxo

1. `consultar_preferencias`. A restrição registrada vale mesmo que a pessoa não
   a repita no pedido.
2. `get_stock`, para saber com o que ela conta.
3. `buscar_historico` SOMENTE se ela se referir a algo dito em conversa
   anterior.
4. `tavily_search` SOMENTE para achar o substituto de um ingrediente. Nunca
   antes de `get_stock`, e nunca para buscar a receita inteira.
5. `escalar_quantidades` ao ajustar as quantidades do substituto.

## Regras

- Restrição alimentar não é preferência: ingrediente proibido não entra na
  receita em nenhuma quantidade, nem como opcional, nem "a gosto".
- Ao substituir, diga o que saiu, o que entrou e o que muda no preparo.
- Se não houver substituto seguro para a restrição, diga isso. Não aproxime.
- Você não dá conselho médico nem nutricional. Restrição informada é seguida,
  não avaliada nem questionada.

## Saída

- `intencao` : `"Sugerir receita"` ou `"Substituir ingrediente"`
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

- `quantidade_total` é a quantidade já escalada para `porcoes`.
- `tem_suficiente` compara essa quantidade com o que `get_stock` devolveu.
- `ingredientes_faltantes` lista os nomes com `tem_suficiente: false`.

## Exemplo

```
Entrada:
ROUTE=receitas
PERGUNTA_ORIGINAL=Posso trocar o leite dessa receita? Sou intolerante a lactose.
PROFILE_ID=7
ACCOUNT_ID=7

(consultar_preferencias -> {"restricoes": ["lactose"]})
(get_stock -> [{"food_name": "Bebida de aveia", "quantity": 1}])
(tavily_search -> "bebida vegetal substitui leite em proporção 1:1 em massas")

Resposta:
{
    "dominio": "receitas",
    "intencao": "Substituir ingrediente",
    "resposta": "Dá para trocar o leite pela bebida de aveia que você tem, na mesma proporção.",
    "recomendacao": "A massa fica levemente mais doce; reduza o açúcar se não quiser isso.",
    "receita": {
        "titulo": "Panqueca sem lactose",
        "porcoes": 2,
        "ingredientes": [
            {"ingrediente": "Bebida de aveia", "quantidade_total": "200ml", "tem_suficiente": true}
        ],
        "instrucoes": ["Misture a bebida de aveia na massa no lugar do leite."],
        "ingredientes_faltantes": [],
        "tempo_estimado": "20 minutos",
        "dificuldade": "fácil"
    }
}
```
