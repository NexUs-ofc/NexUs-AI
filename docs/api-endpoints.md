# Mapa inicial da API

## Endpoints próprios

| Método | Rota | Entrada | Saída | Dependências no teste básico |
| --- | --- | --- | --- | --- |
| `GET` | `/` | Nenhuma | Status da aplicação | Nenhuma |
| `POST` | `/chat` | `mensagem`, `session_id` opcional e contexto de conta | `resposta` e `session_id` | O fluxo de IA e os repositórios |

## Endpoints gerados pelo FastAPI

| Rota | Finalidade |
| --- | --- |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | Contrato OpenAPI |

## Contrato atual de `/chat`

O corpo aceito atualmente é:

```json
{
  "mensagem": "Quero uma receita com arroz",
  "session_id": "opcional",
  "household_account_id": 1,
  "account_id": 1
}
```

A resposta é:

```json
{
  "resposta": "Texto retornado pelo agente",
  "session_id": "identificador-da-conversa"
}
```

Os valores padrão `1` para `account_id` e `household_account_id` são
temporários. Na etapa de segurança, eles deverão ser derivados do contexto
autenticado e não aceitos livremente pelo cliente.