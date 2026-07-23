from langchain.tools import tool
from app.repository.mongodb.recipes import RecipesRepository
from app.repository.entities.mongodb.recipe import Recipe


@tool("buscar_receitas_usuario")
def buscar_receitas_usuario(account_id: int) -> str:
    """Busca receitas já salvas para o usuário."""
    receitas = RecipesRepository.get_user_recipes(account_id)

    if not receitas:
        return "Nenhuma receita salva para este usuário."

    linhas = []
    for r in receitas:
        curtida = "Sim" if r.is_liked else "Não"
        linhas.append(f"- {r.title} | Ingredientes: {r.array_ingredients} | Curtida: {curtida}")

    return "\n".join(linhas)


@tool("salvar_receita")
def salvar_receita(titulo: str, ingredientes: str, instrucoes: str, account_id: int) -> str:
    """Salva uma receita gerada no banco."""
    receita = Recipe(
        title=titulo,
        array_ingredients=ingredientes,
        instructions=instrucoes,
    )

    resultado = RecipesRepository.create_recipe(receita, account_id)

    if resultado is None:
        return "Erro ao salvar receita."

    return f"Receita '{resultado.title}' salva com sucesso!"
