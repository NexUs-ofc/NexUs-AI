---
name: Receita com restrição
description: Adapta ou confere uma receita existente conforme restrições, substituições ou pedido de completar/corrigir. Use para alergia, dieta, intolerância, troca de ingrediente ou para revisar uma receita cuja informação esteja incompleta.
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
ingrediente, pede para trocar um ingrediente específico, ou pede para revisar,
completar ou corrigir uma receita existente.

A restrição do perfil vem na linha RESTRICOES da entrada e vale mesmo que a
pessoa não a repita no pedido.

## Fluxo

1. Leia RESTRICOES (restrições do perfil) e PREFERENCIAS (gostos) da entrada.
   Ingrediente restrito ou que a pessoa diz não gostar sai da receita.
2. `get_stock`, para saber com o que ela conta.
3. `buscar_historico` SOMENTE se ela se referir a algo dito em conversa
   anterior.
4. Use `tavily_search` SOMENTE para achar o substituto de um ingrediente. Nunca
   antes de `get_stock`, e nunca para buscar a receita inteira. Se a ferramenta
   não estiver disponível, não diga que pesquisou nem invente fonte ou
   confirmação: sugira apenas uma substituição culinária comum que conheça com
   segurança. Se não tiver confiança, diga que não consegue confirmar um
   substituto adequado.
5. `escalar_quantidades` ao ajustar as quantidades do substituto.

## Regras

- Restrição alimentar não é preferência: ingrediente proibido não entra na
  receita em nenhuma quantidade, nem como opcional, nem "a gosto".
- Ao substituir, diga o que saiu, o que entrou e o que muda no preparo.
- Ao revisar uma receita, preserve o prato e avalie somente a lacuna indicada.
  Se houver uma receita completa no pedido ou no histórico, não a troque por
  uma sugestão do estoque. Se só houver uma referência vaga (por exemplo,
  "o preparo usa sal, mas não informa a quantidade") e não houver receita no
  pedido nem no histórico, diga que precisa ver a receita para completá-la com
  segurança. Não invente outro prato nem trate essa solicitação como receita
  nova baseada no estoque.
- "Está completa para ser salva?" é uma pergunta de avaliação, não autorização
  para salvar. Explique o que está presente ou falta e nunca chame ferramenta
  de gravação sem pedido explícito para salvar.
- Quando a receita fornecida tiver dados suficientes para sugerir uma
  quantidade ausente, identifique o valor como sugestão culinária, explique a
  referência usada e não afirme que era o valor original da receita.
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
