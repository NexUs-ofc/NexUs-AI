---
name: Atualização guiada do estoque
description: Conduz a pessoa passo a passo para refazer o estoque inteiro, perguntando sobre o que mudou até terminar. É a funcionalidade principal do estoque.
metadata:
  dominio: stock
  rota: estoque
  intencao: Atualizar estoque completo
  ferramentas: [get_stock, get_expired_products, get_missing_products, resolver_alimento, resolver_data, add_product, remove_product]
  version: 1.0.0
---

# Atualização guiada do estoque

## Quando assumir esta skill

A pessoa quer refazer o estoque inteiro: "quero atualizar meu estoque", "vamos
revisar o que eu tenho", "cheguei do mercado".

Para um item só, use `estoque-registrar`. Esta skill é o fluxo longo, de vários
turnos.

## Fluxo

Na primeira mensagem, levante o panorama antes de perguntar qualquer coisa:

1. `get_stock` para o estoque atual.
2. `get_expired_products` para o que está vencendo.
3. `get_missing_products` para o que está em falta.
4. Diga que vai usar esse panorama, e comece perguntando pelo mais urgente:
   os produtos próximos do vencimento.

A cada resposta dela:

5. Registre o que mudou com `resolver_alimento` + `add_product`, ou com
   `remove_product`.
6. **Pergunte automaticamente se há mais alguma coisa**, e siga para o próximo
   grupo.
7. Repita até ela dizer que acabou.

## Regras

- Uma pergunta por vez. Lista de dez perguntas de uma vez faz a pessoa
  desistir.
- Siga uma ordem que faça sentido: primeiro o que vence, depois o que faltava,
  depois o resto.
- **Registre conforme ela fala**, não acumule tudo para o fim. Se a conversa
  cair, o que já foi dito está salvo.
- Nunca pergunte unidade de medida, marca ou categoria. Nome, quantidade e
  validade bastam.
- Se ela não souber a validade de um item, registre sem ela em vez de travar.
- Se ela quiser parar no meio, pare. Diga o que foi registrado até ali e não
  insista.
- Nunca repita uma pergunta que ela já respondeu nesta conversa.

## Saída

- `intencao` : `"Atualizar estoque completo"`

Nesta skill, `acompanhamento` quase sempre existe: é a próxima pergunta do
roteiro. `recomendacao` e `acompanhamento` não podem dizer a mesma coisa.

## Exemplos

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Quero atualizar meu estoque.
PROFILE_ID=7

(get_stock -> [...])
(get_expired_products -> [{"food_name": "Iogurte", "quantity": 2, "expiry_date": "2026-10-06"}])
(get_missing_products -> [{"food_name": "Arroz"}])

Resposta:
{
    "dominio": "stock",
    "intencao": "Atualizar estoque completo",
    "resposta": "Levantei seu estoque, o que está vencendo e o que está em falta.",
    "recomendacao": "Vamos começar pelo que vence antes.",
    "acompanhamento": "Você ainda tem os 2 iogurtes que vencem amanhã, ou já consumiu?"
}
```

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Consumi os dois.
PROFILE_ID=7

(get_stock -> [...])
(remove_product -> ok)

Resposta:
{
    "dominio": "stock",
    "intencao": "Atualizar estoque completo",
    "resposta": "Baixei os 2 iogurtes do seu estoque.",
    "recomendacao": "",
    "acompanhamento": "O arroz estava em falta. Você comprou?"
}
```
