from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.schemas.flow import app as graph_app
from app.repository.mongodb.conversations import ConversationRepository

teste = FastAPI(title="NexUs-AI")

# Resquest
class ChatRequest(BaseModel):
    mensagem: str
    account_id: int


#  Response
class ChatResponse(BaseModel):
    resposta: str
    historico: list[dict]

@teste.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    #Busca histórico da tabela de regstro
    historico = ConversationRepository.get_history(req.account_id)

    #monta o estado e roda o grafo
    resultado = graph_app.invoke({
        "mensagem": req.mensagem,
        "historico": historico,
        "rota": "",
        "resposta_agente": "",
        "resposta_final": "",
        "entrada_aprovada": False,
        "saida_aprovada": False,
        "mapa_pii": {},
        "household_account_id": req.household_account_id,
        "account_id": req.account_id,
    })

    resposta = resultado["resposta_final"]

    # salva banco
    ConversationRepository.append_messages(req.account_id, [
        {"role": "user", "content": req.mensagem},
        {"role": "assistant", "content": resposta},
    ])

    #retorna
    historico_atualizado = historico + [
        {"role": "user", "content": req.mensagem},
        {"role": "assistant", "content": resposta},
    ]

    return ChatResponse(
        resposta=resposta,
        historico=historico_atualizado,
    )