from langchain.tools import tool
from app.repository.mongo.recipe_repository import RecipeRepository

repo = RecipeRepository()


@tool("buscar_receitas_usuario")
def buscar_receitas_usuario(account_id: int) -> str:
    """Busca receitas já salvas para o usuário."""
    receitas = repo.buscar_receitas_usuario(account_id)

    if not receitas:
        return "Nenhuma receita salva para este usuário."

    linhas = []
    for r in receitas:
        curtida = "Sim" if r.get("is_liked") else "Não"
        linhas.append(f"- {r['title']} | Ingredientes: {r['array_ingredients']} | Curtida: {curtida}")

    return "\n".join(linhas)


@tool("salvar_receita")
def salvar_receita(titulo: str, ingredientes: str, instrucoes: str, account_id: int) -> str:
    """Salva uma receita gerada no banco."""
    receita = repo.salvar_receita(titulo, ingredientes, instrucoes, account_id)
    return f"Receita '{receita['title']}' salva com sucesso!"
