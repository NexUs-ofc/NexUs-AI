from langchain.tools import tool
from ..repository.mongodb.recipes import RecipesRepository
from ..model.mongodb.recipe import Recipe


@tool("buscar_receitas_usuario")
def buscar_receitas_usuario(account_id: int) -> str:
    """Busca receitas já salvas para o usuário."""
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
    account_id: int,
) -> str:
    """
    Salva uma receita gerada no banco.

    Parâmetros:
        - titulo: Título da receita.
        - serving_size: Quantidade de pessoas que a receita foi pensada para servir.
        - ingredientes: Lista no formato [{"food_id": int, "required_quantity": str, "mandatory": bool, "possible_substitutes": list[int]}].
        - instrucoes: Modo de preparo.
        - account_id: Identificador da conta do usuário.
    """
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