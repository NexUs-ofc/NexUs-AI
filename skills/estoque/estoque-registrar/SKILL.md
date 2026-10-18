---
name: Registrar no estoque
description: Adiciona e remove produtos do estoque. Use quando a pessoa diz que comprou, consumiu, descartou ou acabou alguma coisa.
metadata:
  dominio: stock
  rota: estoque
  intencao: Adicionar produto ao estoque | Remover produto de estoque
  ferramentas: [resolver_alimento, resolver_data, estimar_validade, add_product, remove_product, get_stock]
  version: 1.0.0
---

# Registrar no estoque

## Quando assumir esta skill

A pessoa diz que comprou, consumiu, descartou ou acabou alguma coisa:
"comprei 2 pacotes de arroz", "acabou o leite", "joguei fora o tomate".

Se ela quer refazer o estoque inteiro, use `estoque-atualizacao-guiada`.

## Fluxo

**Para adicionar:**

1. `resolver_alimento` com o nome que a pessoa falou. Ele devolve o `food_id`
   e **cadastra o alimento se ele não existir no catálogo**.
2. Validade:
   - a pessoa deu data exata: use a data;
   - deu por extenso ("semana que vem", "daqui 3 meses"): `resolver_data`;
   - não deu data e o produto não veio de nota: `estimar_validade`.
3. `add_product` com o `food_id` que voltou.

Chame `resolver_alimento` e `estimar_validade` (ou `resolver_data`) **juntos,
na mesma etapa**: uma não depende da outra, e cada etapa a mais reenvia o
prompt inteiro e faz a resposta demorar.

**Para remover:**

1. `get_stock` e encontre o item cujo `food_name` corresponde ao que a pessoa
   mencionou.
2. `remove_product` com o `pantry_item_id` desse item.

## Validade quando o produto não tem data exata

Vale para item sem data dada pela pessoa e sem nota fiscal (tomate, maçã,
verdura).

1. Chame **sempre** `estimar_validade(produto, guarda)`. Não estime de cabeça,
   nem quando achar que sabe: a tool pesquisa e confere a fonte.
   `guarda` é onde o produto fica: "geladeira" (padrão), "temperatura
   ambiente" ou "congelador". Se a pessoa não disse, use o habitual do produto.
2. Se voltar `validade`, passe essa data para `add_product`, sem refazer conta.
3. Se voltar `dias` nulo, chame `add_product` sem `expiry_date` e diga que não
   achou um prazo seguro.
4. Na resposta, diga o prazo, a guarda e a `fonte` **exatamente como a tool
   devolveu**. Ex.: "Maçã na geladeira: 30 dias (fonte: <fonte>). Validade
   17/11/2026."

Nunca cite fonte, site ou prazo que não veio de `estimar_validade` nesta
rodada. Não pergunte à pessoa se pode estimar: a estimativa é o trabalho dela.

## Regras

- **Alimento fora do catálogo não é impedimento.** `resolver_alimento`
  cadastra. Nunca diga que o alimento não existe no sistema.
- Se `resolver_alimento` devolver `ambiguo`, pergunte qual das opções antes de
  seguir.
- Para adicionar você precisa de nome e quantidade. A validade é pedida **só
  quando o produto tem data de vencimento** (leite, iogurte, carne embalada).
  Produto sem data exata — tomate, verdura, legume, fruta a granel — não pergunte
  a validade: siga a seção "Validade quando o produto não tem data exata".
  Não pergunte unidade de medida,
  marca, categoria, local de armazenamento nem preço — `add_product` não recebe
  esses dados, e perguntar só faz ela perder tempo.
- Nunca pergunte `food_id` nem `pantry_item_id`. Você resolve os dois sozinho.
- Se ela já deu nome, quantidade e validade, **execute**. Não peça confirmação
  de dado que ela acabou de informar.
- Mesmo alimento com a mesma validade soma na linha que já existe. Isso é
  automático; não avise sobre o detalhe.
- **Só diga "adicionei" depois de `add_product` ter respondido nesta rodada.**
  Sem a chamada, nada foi gravado.

## Saída

- `intencao` : `"Adicionar produto ao estoque"` ou
  `"Remover produto de estoque"`

## Exemplo

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Adiciona 2 pés de alface no meu estoque, validade 20/10/2026.

(resolver_alimento(nome="alface") -> {"food_id": 145, "food_name": "alface", "criado": true})
(add_product(food_id=145, quantity=2, expiry_date="20/10/2026") -> ok)

Resposta:
{
    "dominio": "stock",
    "intencao": "Adicionar produto ao estoque",
    "resposta": "Adicionei 2 pés de alface ao seu estoque, com validade em 20/10/2026.",
    "recomendacao": "",
    "acompanhamento": "Tem mais alguma coisa para registrar?"
}
```
