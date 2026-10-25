---
name: Receitas anteriores
description: Salva uma receita, lista as receitas salvas ou recupera uma receita dada antes. Use SOMENTE quando a pessoa pedir para salvar ou guardar uma receita, quiser ver as receitas salvas, ou pedir de novo uma receita que você já deu ("a receita de bolo que você me passou ontem"). Pedido de receita nova NÃO é desta skill.
metadata:
  dominio: receitas
  rota: receitas
  intencao: Salvar receita | Buscar receita anterior
  ferramentas: [buscar_receitas_usuario, buscar_historico, salvar_receita]
  version: 1.0.0
---

# Receitas anteriores

## Quando assumir esta skill

- A pessoa pede para salvar ou guardar uma receita ("salva essa receita").
- A pessoa quer ver as receitas que salvou.
- A pessoa pede de novo uma receita que você já deu ("me passa de novo a
  receita de pudim que você me deu semana passada").

Pedido de receita nova não é desta skill.

## Fluxo

1. Para salvar: a receita está no histórico da conversa, normalmente a última
   que você deu. Chame `salvar_receita` com ela como foi dada: título,
   porções, cada ingrediente como {"nome", "quantidade"}, o modo de preparo,
   tempo_preparo_minutos (minutos inteiros) e dificuldade (fácil, média ou difícil).
   Reutilize tempo e dificuldade da receita apresentada; não os invente ao salvar.
   Não informe food_id: ingredientes são salvos pelo nome, sem criar alimentos. Se
   houver mais de uma e não der para saber qual, pergunte em `esclarecer`.
2. Para ver as salvas: `buscar_receitas_usuario`.
3. Para recuperar uma receita dada antes: `buscar_receitas_usuario` primeiro;
   se ela não estiver lá, `buscar_historico` com o nome da receita.

## Regras

- Nunca salve sem a pessoa pedir.
- Ao consultar uma receita salva, mantenha o objeto receita com título, porções, todos os ingredientes e instruções. Não omita ingredientes nem reescreva a receita para outra versão.
- Não invente receita. Se não achar nem nas salvas nem no histórico, diga que
  não encontrou e ofereça gerar uma nova.
- Se `salvar_receita` falhar, diga que não salvou. Nunca confirme sucesso sem o retorno da ferramenta.
- Salve TODOS os ingredientes e passos, sem resumir quantidades ou modo de preparo.
- Se não houver receita completa na conversa nem nas salvas, peça qual receita deseja guardar; não gere outra no lugar.
- `buscar_receitas_usuario` devolve conteúdo completo e id. Para mostrar uma receita, repasse ingredientes, porções, preparo, tempo e dificuldade que existem. Campo ausente em receita antiga é desconhecido, não motivo para inventar.
- Se a pessoa disser só “salva essa”, use a última receita apresentada, sem pedir confirmação de novo.

## Saída

- `intencao` : `"Salvar receita"` ou `"Buscar receita anterior"`

## Exemplo

```
Entrada:
ROUTE=receitas
PERGUNTA_ORIGINAL=Salva essa receita pra mim.

(histórico: você deu "Macarrão ao sugo", 2 porções)
(salvar_receita -> "Receita 'Macarrão ao sugo' salva com sucesso!")

Resposta:
{
    "dominio": "receitas",
    "intencao": "Salvar receita",
    "resposta": "Salvei o Macarrão ao sugo nas suas receitas.",
    "recomendacao": "Quando quiser, é só pedir para ver suas receitas salvas."
}
```
