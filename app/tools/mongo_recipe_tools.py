import json
import re
import unicodedata

from langchain.tools import tool
from pydantic import StrictInt

from ..auth import identidade
from ..model.mongodb.recipe import Recipe, validate_steps
from ..repository.mongodb.recipes import RecipesRepository, RecipeUnavailable
from ..validation import (
    ingredientes_basicos_ausentes,
    inteiro_positivo,
    validar_quantidade_receita,
    validar_titulo,
)


def _difficulty(value: str) -> str:
    normalized = "".join(
        c for c in unicodedata.normalize("NFKD", value.strip().lower())
        if not unicodedata.combining(c)
    )
    mapping = {"facil": "easy", "easy": "easy", "media": "medium", "medio": "medium",
               "medium": "medium", "dificil": "hard", "hard": "hard"}
    if normalized not in mapping:
        raise ValueError("Informe dificuldade fácil, média ou difícil.")
    return mapping[normalized]


@tool("buscar_receitas_usuario")
def buscar_receitas_usuario(titulo: str = "") -> str:
    """Consulta receitas salvas com título, id, ingredientes, preparo, tempo e dificuldade.
    titulo: filtro opcional pelo nome da receita; sem filtro mostra as mais recentes.
    Nunca invente o conteúdo quando a consulta falhar.
    """
    try:
        recipes = RecipesRepository.get_user_recipes(identidade.conta(), titulo=titulo)
    except RecipeUnavailable:
        return "FALHA: não foi possível consultar as receitas salvas; tente novamente."
    return json.dumps([r.to_dict() for r in recipes], ensure_ascii=False, default=str)


@tool("salvar_receita")
def salvar_receita(
    titulo: str,
    serving_size: StrictInt,
    ingredientes: list[dict],
    instrucoes: str,
    tempo_preparo_minutos: StrictInt,
    dificuldade: str,
    Step: list[dict] | None = None,
) -> str:
    """Salva SOMENTE uma receita completa que a pessoa pediu para guardar.
    titulo: nome da receita dada na conversa, sem inventar uma nova.
    serving_size: número positivo de porções.
    ingredientes: [{"nome": "Arroz", "quantidade": "200 g"}], todos com quantidade positiva e unidade, ou 'a gosto'.
      Também aceita ingrediente/quantidade_total do objeto receita. Sem cadastrar alimentos.
    instrucoes: modo de preparo completo, com um passo por linha.
    Step: lista ordenada de {"title": "Titulo da etapa", "description": "Preparo completo da etapa"}.
      Inclua todos os passos da receita, sem inventar nem resumir o preparo.
    tempo_preparo_minutos: tempo total estimado em minutos inteiros positivos.
    dificuldade: fácil, média ou difícil. Reutilize os dados da receita apresentada.
    Se a receita anterior não estiver completa, pergunte o que falta antes de salvar.
    """
    try:
        titulo = validar_titulo(titulo)
        if not titulo.strip() or not instrucoes.strip() or serving_size <= 0 or tempo_preparo_minutos <= 0:
            raise ValueError("Título, preparo, porções e tempo são obrigatórios.")
        inteiro_positivo(serving_size, "Porcoes")
        inteiro_positivo(tempo_preparo_minutos, "Tempo de preparo")
        saved_ingredients = []
        for item in ingredientes:
            if not isinstance(item, dict):
                raise TypeError("Informe nome e quantidade de cada ingrediente.")
            name = str(item.get("nome") or item.get("ingrediente") or item.get("name") or "").strip()
            raw = next((item[key] for key in ("quantidade", "quantidade_total", "required_quantity")
                        if key in item), None)
            quantity = validar_quantidade_receita(raw, item.get("unidade") or item.get("unitOfMeasure") or "")
            if not name or not quantity:
                raise ValueError("Informe nome e quantidade de todos os ingredientes.")
            saved_ingredients.append({
                "name": name, "required_quantity": quantity,
                "mandatory": item.get("mandatory", item.get("obrigatorio", True)),
            })
        if not saved_ingredients:
            raise ValueError("A receita precisa de ingredientes.")
        missing = ingredientes_basicos_ausentes(saved_ingredients, instrucoes)
        if missing:
            raise ValueError("Ingredientes usados no preparo sem quantidade na lista: " + ", ".join(missing))
        steps = validate_steps(Step if Step is not None else [
            {"title": f"Etapa {index}",
             "description": re.sub(r"^\s*\d+[.)]\s*", "", line).strip()}
            for index, line in enumerate(
                (line for line in instrucoes.splitlines() if line.strip()), start=1,
            )
        ])
        missing_steps = ingredientes_basicos_ausentes(saved_ingredients, "\n".join(
            step["description"] for step in steps
        ))
        if missing_steps:
            raise ValueError("Ingredientes das etapas sem quantidade: " + ", ".join(missing_steps))
        recipe = Recipe(
            title=titulo.strip(), serving_size=serving_size, ingredients=saved_ingredients,
            instructions=instrucoes.strip(), account_id=identidade.conta(),
            preparation_time_minutes=tempo_preparo_minutos, difficulty=_difficulty(dificuldade),
            Step=steps,
        )
        recipe.mark_created()
    except (ValueError, TypeError) as error:
        return f"FALHA: receita não salva. {error}"

    result = identidade.executar_gravacao(
        "salvar_receita", recipe.to_dict(), lambda: RecipesRepository.create_recipe(recipe),
    )
    if result is None:
        return "FALHA: não foi possível salvar a receita. Tente novamente."
    return json.dumps({"status": "sucesso", "receita": result.to_dict()}, ensure_ascii=False, default=str)
