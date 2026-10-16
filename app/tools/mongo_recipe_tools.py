from langchain.tools import tool

from ..auth import identidade
from ..model.mongodb.recipe import Recipe
from ..repository.mongodb.recipes import RecipesRepository


@tool("buscar_receitas_usuario")
def buscar_receitas_usuario() -> str:
    """Busca receitas já salvas para o usuário."""
    account_id = identidade.conta()

    receitas = RecipesRepository.get_user_recipes(account_id)

    if not receitas:
        return "Nenhuma receita salva para este usuário."

    linhas = []
    for r in receitas:
        curtida = "Sim" if r.is_liked else "Não"
        linhas.append(f"- {r.title} | Serve: {r.serving_size} pessoas | Ingredientes: {r.ingredients} | Curtida: {curtida}")

    return "\n".join(linhas)


@tool("salvar_receita")
def salvar_receita(
    titulo: str,
    serving_size: int,
    ingredientes: list[dict],
    instrucoes: str,
) -> str:
    """
    Salva uma receita gerada no banco.

    Parâmetros:
        - titulo: Título da receita.
        - serving_size: Quantidade de pessoas que a receita foi pensada para servir.
        - ingredientes: Lista no formato [{"food_id": int, "required_quantity": str, "mandatory": bool, "possible_substitutes": list[int]}].
        - instrucoes: Modo de preparo.
    """
    account_id = identidade.conta()

    receita = Recipe(
        title=titulo,
        serving_size=serving_size,
        ingredients=ingredientes,
        instructions=instrucoes,
    )

    resultado = RecipesRepository.create_recipe(receita, account_id)

    if resultado is None:
        return "Erro ao salvar receita."

    return f"Receita '{resultado.title}' salva com sucesso!"