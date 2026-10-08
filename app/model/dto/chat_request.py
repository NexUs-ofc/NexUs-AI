from pydantic import BaseModel, Field

# Uma mensagem sem teto vai inteira para o modelo: estoura o contexto e queima
# a cota do dia numa requisicao. O limite e generoso para texto de conversa e
# barra colagem de arquivo.
LIMITE_MENSAGEM = 2000


class ChatRequest(BaseModel):
    mensagem: str = Field(min_length=1, max_length=LIMITE_MENSAGEM)
    session_id: str | None = Field(default=None, max_length=64)
    household_account_id: int = Field(default=1, ge=1)
    account_id: int = Field(default=1, ge=1)
