from langchain.tools import tool

from app.auth import identidade
from app.repository.qdrant.memory_repository import MemoryRepository


@tool("buscar_historico")
def buscar_historico(busca: str) -> str:
    """Consulta conversas ANTERIORES do usuário, já encerradas.

    Use somente quando a resposta depender de algo dito numa conversa passada:
    preferências, restrições alimentares, decisões ou planos que o usuário
    mencionou antes. NÃO use para dados que estão no banco (estoque, receitas
    salvas, eventos) — para isso existem as tools específicas.

    Args:
        busca: assunto a procurar nos resumos das conversas anteriores.
    """
    account_id = identidade.conta()


    resumos = MemoryRepository.buscar_resumos(
        account_id=account_id,
        busca=busca,
        limite=5,
    )

    if not resumos:
        return "Nenhuma conversa anterior relevante encontrada."

    linhas = []

    for item in resumos:
        data = str(item.get("created_at", ""))[:10]
        linhas.append(f"[{data}] {item['resumo']}")

    return "\n\n".join(linhas)
