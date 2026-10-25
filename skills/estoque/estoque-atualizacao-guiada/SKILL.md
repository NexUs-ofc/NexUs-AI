---
name: Revisão guiada do estoque
description: Conduz a pessoa passo a passo para revisar o estoque e registrar remoções. Use quando ela quer conferir o que mudou no estoque.
metadata:
  dominio: stock
  rota: estoque
  intencao: Revisar estoque
  ferramentas: [get_stock, get_expired_products, get_missing_products, remove_product]
  version: 1.0.0
---

# Revisão guiada do estoque

## Quando assumir esta skill

A pessoa quer revisar o estoque: "quero atualizar meu estoque", "vamos
revisar o que eu tenho".

O chat não adiciona produtos. Se ela disser que comprou algo, deixe claro que
essa inclusão não pode ser feita por aqui e continue apenas com a revisão.

## Fluxo

Na primeira mensagem, levante o panorama antes de perguntar qualquer coisa:

1. `get_stock` para o estoque atual.
2. `get_expired_products` para o que está vencendo.
3. `get_missing_products` para o que está em falta.
4. Diga que vai usar esse panorama, e comece perguntando pelo mais urgente:
   os produtos próximos do vencimento.

A cada resposta dela:

5. Registre as remoções confirmadas com `remove_product`.
6. **Pergunte automaticamente se há mais alguma coisa**, e siga para o próximo
   grupo.
7. Repita até ela dizer que acabou.

## Regras

- Uma pergunta por vez. Lista de dez perguntas de uma vez faz a pessoa
  desistir.
- Siga uma ordem que faça sentido: primeiro o que vence, depois o que faltava,
  depois o resto.
- **Registre as remoções conforme ela confirma**, não acumule tudo para o fim.
  Se a conversa cair, o que já foi removido continua salvo.
- Nunca pergunte unidade de medida, marca ou categoria. Nome, quantidade e
  validade bastam.
- Se ela pedir para incluir um produto, não peça detalhes: explique que o chat
  não realiza inclusões.
- Se ela quiser parar no meio, pare. Diga o que foi registrado até ali e não
  insista.
- Nunca repita uma pergunta que ela já respondeu nesta conversa.

## Saída

- `intencao` : `"Revisar estoque"`

Nesta skill, `acompanhamento` quase sempre existe: é a próxima pergunta do
roteiro. `recomendacao` e `acompanhamento` não podem dizer a mesma coisa.

## Exemplos

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Quero atualizar meu estoque.

(get_stock -> [...])
(get_expired_products -> [{"food_name": "Iogurte", "quantity": 2, "expiry_date": "2026-10-06"}])
(get_missing_products -> [{"food_name": "Arroz"}])

Resposta:
{
    "dominio": "stock",
    "intencao": "Revisar estoque",
    "resposta": "Levantei seu estoque, o que está vencendo e o que está em falta.",
    "recomendacao": "Vamos começar pelo que vence antes.",
    "acompanhamento": "Você ainda tem os 2 iogurtes que vencem amanhã, ou já consumiu?"
}
```

```
Entrada:
ROUTE=stock
PERGUNTA_ORIGINAL=Consumi os dois.

(get_stock -> [...])
(remove_product -> ok)

Resposta:
{
    "dominio": "stock",
    "intencao": "Revisar estoque",
    "resposta": "Baixei os 2 iogurtes do seu estoque.",
    "recomendacao": "",
    "acompanhamento": "O arroz estava em falta. Você comprou?"
}
```
