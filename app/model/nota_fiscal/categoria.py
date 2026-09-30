from enum import StrEnum


class CategoriaProduto(StrEnum):
    """
    Categorias aceitas para itens de nota fiscal.

    É a única fonte de verdade: o prompt do leitor, o schema de saída do agente
    e a validação do endpoint de confirmação usam este ENUM. Nenhuma categoria
    fora dele é criada no Postgres.
    """

    HORTIFRUTI = "Hortifruti"
    ACOUGUE = "Açougue"
    PADARIA = "Padaria"
    LATICINIOS = "Laticínios"
    HIGIENE = "Higiene"
    LIMPEZA = "Limpeza"
    BEBIDAS = "Bebidas"
    MERCEARIA = "Mercearia"
    CONGELADOS = "Congelados"
    ENLATADOS = "Enlatados"
    DOCES = "Doces e Sobremesas"
    PET = "Pet"
    OUTROS = "Outros"
