---
name: Receita do estoque
description: Gera uma receita nova, usando o estoque de hoje e priorizando o que vence primeiro. Use quando a pessoa pede uma receita nova, de um prato específico ("receita de pudim") ou a partir do que ela tem em casa.
metadata:
  dominio: receitas
  rota: receitas
  intencao: Sugerir receita
  ferramentas: [ingredientes_para_comprar, consultar_preferencias, get_stock, escalar_quantidades]
  version: 1.0.0
---

# Receita do estoque

## Quando assumir esta skill

A pessoa pede uma receita nova: um prato específico ("receita de pudim"), uma
sugestão a partir do que ela já tem em casa, ou algo para aproveitar o que
está vencendo.

Não assuma esta skill se houver restrição alimentar ou pedido de substituição
(use `receita-com-restricao`), nem se a entrada trouxer `CHAMADO_POR=events`
(use `receita-para-evento`).

## Fluxo

1. As restrições do perfil já vêm na linha RESTRICOES e as preferências na
   linha PREFERENCIAS da entrada. Comece direto por
   `get_stock` — não gaste uma rodada pedindo o que já está na sua frente.
2. `get_stock` já traz a validade de cada item, e você tem a data de hoje no
   contexto. O que está vencido ou vencendo sai dessa lista por comparação —
   não existe ferramenta a chamar para isso.
3. Preserve primeiro o objetivo explícito. Se a pessoa pediu um prato ou tipo
   específico ("uma carne gostosa"), faça esse prato. Se pediu explicitamente
   uma receita com o que há no estoque, use os itens confirmados como base,
   mesmo que sejam poucos ou pouco variados: escolha o preparo culinariamente
   mais coerente que realmente os use e explique a limitação. Se pediu apenas
   uma sugestão aberta, escolha uma receita adequada ao perfil. Considere os
   itens compatíveis como preferência, mas não sacrifique a qualidade nem force
   uma combinação estranha quando o estoque tiver pouca variedade. Só trate o
   uso do estoque como requisito quando a pessoa pedir explicitamente uma receita
   com o que tem nele.
4. `escalar_quantidades` SOMENTE se a pessoa pediu um número de porções
   diferente do da receita.

## Regras

- **Prioridade, não exclusão:** use primeiro o de validade mais curta que
  ainda não venceu, mas o resto do estoque continua disponível e entra quando
  a receita pede. Não faça prato pobre só para gastar o que vence antes.
- **PREFERENCIAS escolhe o prato**, validade só ordena dentro do que é
  compatível. Restrição alimentar nunca cede para aproveitar validade.
- **Vencido não entra na receita** (compare `expiry_date` com a data de hoje),
  nem nos ingredientes nem nas `instrucoes`. Cite uma vez no fim, para
  descarte.
- Quando o pedido exigir usar o estoque e houver poucos itens compatíveis,
  procure um preparo real que use o melhor deles (por exemplo, bebida ou
  sobremesa se só houver achocolatado), sem inventar combinações. Diga qual é
  a limitação e o que falta. Não descarte o objetivo em favor de uma receita
  genérica que ignora os itens disponíveis.
- O estoque é base, não prisão. Se a pessoa pediu um prato, faça esse
  prato: o que ela não tem entra em `ingredientes_faltantes` e, em
  `recomendacao`, diga o que comprar ou o que do estoque substitui. Nunca
  finja que tem o que falta.
- Item do estoque só entra se combina com o prato. Não force ingrediente na
  receita só porque ele está em casa.
- Em pedido aberto sem exigência de usar o estoque, escolha primeiro um prato
  coerente e agradável. Se os poucos itens disponíveis não derem uma boa receita,
  deixe o estoque de lado em vez de inventar uma mistura; não afirme que os
  ingredientes escolhidos estão disponíveis sem confirmação.
- Ingrediente que a pessoa não tem entra em `ingredientes_faltantes`, nunca
  some da lista.
- Se o estoque estiver vazio ou não der prato, sugira uma receita simples
  guiada por PREFERENCIAS, com tudo em `ingredientes_faltantes`, e ofereça
  montar a lista de compras.

## Arbitragem de combinações

Antes de fechar a receita, rascunhe duas ideias e escolha uma. Primeiro descarte
as que não atendem ao objetivo e às restrições explícitos. Entre as restantes,
prefira uma combinação culinariamente coerente que realmente aproveite o estoque
quando isso foi pedido. Desconte pontos por ingredientes sem função e compras
desnecessárias; nunca use mais itens como único critério de escolha.
Mostre somente a opção escolhida, salvo se a pessoa pedir alternativas.

- Se a pessoa nomear um prato ou ingrediente, ele é a âncora da receita. Não troque
  o pedido para consumir algo aleatório que esteja na despensa.
- Produtos da mesma função culinária não contam como diversidade. Nescau e Nesquik
  juntos continuam sendo uma família de achocolatado; escolha um só.
- Com estoque de achocolatado sem leite, prefira uma bebida ou sobremesa coerente,
  marque leite como compra se a receita precisar dele e não o declare disponível.
- Se o estoque não tiver variedade para uma refeição, diga isso diretamente e escolha
  um lanche/bebida real que use o item disponível. Não invente prato principal.
- Pedido de arroz sem arroz no estoque continua sendo uma receita de arroz com o arroz
  marcado para compra; não use achocolatado como substituto nem alegue que veio do estoque.
- Pedido de abóbora mantém a abóbora como protagonista e não combina com achocolatado.

## Conferência antes de responder

- Depois de escolher a receita, use `ingredientes_para_comprar` com ingredientes, quantidades e unidades para conferir o estoque. A ferramenta soma lotes e converte g/kg e ml/l. Nunca marque como suficiente só porque existe um pacote.
- Se a comparação não for confirmada, não afirme suficiência: avise que a quantidade disponível precisa ser conferida. Não converta xícaras ou pitadas em gramas por palpite.
- Todas as sugestões incluem porções, ingredientes com quantidades, passos completos, tempo_preparo_minutos e dificuldade. Tempo é estimativa culinária, não prazo garantido.

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
    tempo_preparo_minutos: 30,
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
RESTRICOES=nenhuma restrição registrada

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
