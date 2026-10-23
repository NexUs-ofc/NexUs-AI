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
        linhas.append(f"- {r.title} | Serve: {r.serving_size} pessoas | Ingredientes: {r.ingredients}")

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

    Use SOMENTE quando a pessoa pedir para salvar ("salva essa receita").
    Sugerir receita não é motivo para salvar.

    Parâmetros:
        - titulo: Título da receita.
        - serving_size: Quantidade de pessoas que a receita foi pensada para servir.
        - ingredientes: Lista no formato [{"nome": str, "quantidade": str}],
          com o nome do alimento como aparece na receita. Ex:
          [{"nome": "Picanha", "quantidade": "500 g"}]. Não informe id.
        - instrucoes: Modo de preparo.
    """
    account_id = identidade.conta()

    # Ingrediente vai pelo nome, sem food_id: quem confere o estoque compara
    # o nome com o do alimento (add_recipe).
    ingredientes_salvos = []

    for item in ingredientes:
        if not isinstance(item, dict):
            item = {"nome": item}

        nome = str(
            item.get("nome") or item.get("ingrediente") or item.get("name") or ""
        ).strip()

        if not nome:
            continue

        ingredientes_salvos.append({
            "name": nome,
            "required_quantity": str(
                item.get("quantidade") or item.get("required_quantity") or ""
            ),
            "mandatory": bool(item.get("obrigatorio", item.get("mandatory", True))),
        })

    if not ingredientes_salvos:
        return "Erro ao salvar receita: nenhum ingrediente informado."

    receita = Recipe(
        title=titulo,
        serving_size=serving_size,
        ingredients=ingredientes_salvos,
        instructions=instrucoes,
        account_id=account_id,
    )

    resultado = RecipesRepository.create_recipe(receita)

    if resultado is None:
        return "Erro ao salvar receita."

    return f"Receita '{resultado.title}' salva com sucesso!"