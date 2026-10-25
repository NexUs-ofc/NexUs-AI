---
name: Receita com restrição
description: Adapta a receita à restrição alimentar da pessoa ou troca um ingrediente que ela pediu para substituir. Use quando houver alergia, dieta, intolerância, quando a pessoa disser que não gosta de um ingrediente, ou pedir explicitamente para trocar um ingrediente.
metadata:
  dominio: receitas
  rota: receitas
  intencao: Sugerir receita | Substituir ingrediente
  ferramentas: [ingredientes_para_comprar, consultar_preferencias, get_stock, buscar_historico, tavily_search, escalar_quantidades]
  version: 1.0.0
---

# Receita com restrição

## Quando assumir esta skill

A pessoa tem restrição alimentar, alergia ou dieta, diz que não gosta de um
ingrediente, ou pede para trocar um ingrediente específico da receita.

A restrição do perfil vem na linha RESTRICOES da entrada e vale mesmo que a
pessoa não a repita no pedido.

## Fluxo

1. Leia RESTRICOES (restrições do perfil) e PREFERENCIAS (gostos) da entrada.
   Ingrediente restrito ou que a pessoa diz não gostar sai da receita.
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

## Conferência antes de responder

- Depois de escolher a receita, use `ingredientes_para_comprar` com ingredientes, quantidades e unidades para conferir o estoque. A ferramenta soma lotes e converte g/kg e ml/l. Nunca marque como suficiente só porque existe um pacote.
- Se a comparação não for confirmada, não afirme suficiência: avise que a quantidade disponível precisa ser conferida. Não converta xícaras ou pitadas em gramas por palpite.
- Todas as sugestões incluem porções, ingredientes com quantidades, passos completos, tempo_preparo_minutos e dificuldade. Tempo é estimativa culinária, não prazo garantido.

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
    tempo_preparo_minutos: 30,
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
RESTRICOES=lactose

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
