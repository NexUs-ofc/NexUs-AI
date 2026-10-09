---
name: Criar evento
description: Registra um evento novo - churrasco, aniversário, jantar, reunião - com data, horário, local e quantidade de pessoas. Use quando a pessoa anuncia algo que vai acontecer.
metadata:
  dominio: events
  rota: eventos
  intencao: Criar evento
  ferramentas: [resolver_data, create_event, recomendar_receita]
  version: 1.0.0
---

# Criar evento

## Quando assumir esta skill

A pessoa anuncia algo que vai acontecer: "vou fazer um churrasco sábado",
"tenho um jantar dia 20", "aniversário da minha filha semana que vem".

Se o evento já existe e ela quer alterar ou consultar, use
`evento-gerenciar`.

## Fluxo

1. **`resolver_data` sempre que o dia vier por extenso** — "sábado", "amanhã",
   "dia 20", "próxima terça". Nunca conte o dia da semana de cabeça: é onde o
   erro de um dia aparece. Se devolver `erro`, pergunte a data.
2. Reúna o que falta. São obrigatórios: título, data, duração, local e
   quantidade de pessoas.
3. `create_event` com os dados completos.
4. `recomendar_receita` só se a pessoa pedir sugestão de cardápio.

## Regras

- Pergunte **uma coisa por vez**, e só o que falta para criar. Se ela já disse
  horário e local, não repita a pergunta.
- Nunca invente data, horário, duração nem quantidade de pessoas. Dado de
  evento errado estraga a lista de compras inteira depois.
- Confirme os dados antes de criar, numa frase só.
- Depois de criar, ofereça o próximo passo uma vez: sugerir receitas **ou**
  montar a lista. Não as duas coisas em três frases diferentes.

## Saída

- `intencao` : `"Criar evento"`

```
evento: {
    titulo: "...",
    descricao: "...",
    data: "AAAA-MM-DD",
    inicio: "HH:MM",
    duracao: X,
    fim: "HH:MM",
    local: "...",
    qtd_pessoas: X
}
```

- `data` é a que voltou de `resolver_data`, não a que você calculou.
- `duracao` em minutos.

## Exemplo

```
Entrada:
ROUTE=events
PERGUNTA_ORIGINAL=Vou fazer um churrasco sábado às 12h no quintal pra 10 pessoas, 4 horas.
HOUSEHOLD_ID=1
PROFILE_ID=1
ACCOUNT_ID=1

(resolver_data(referencia="sabado", hora="12h")
    -> {"data": "2026-10-10", "dia_semana": "sábado", "inicio": "2026-10-10T12:00:00"})
(create_event -> {"id": "e1"})

Resposta:
{
    "dominio": "events",
    "intencao": "Criar evento",
    "resposta": "Churrasco criado para sábado, 10/10/2026, das 12:00 às 16:00, no quintal, para 10 pessoas.",
    "recomendacao": "",
    "acompanhamento": "Quer que eu sugira o cardápio?",
    "evento": {
        "titulo": "Churrasco",
        "descricao": "Churrasco para 10 pessoas",
        "data": "2026-10-10",
        "inicio": "12:00",
        "duracao": 240,
        "fim": "16:00",
        "local": "quintal",
        "qtd_pessoas": 10
    }
}
```
