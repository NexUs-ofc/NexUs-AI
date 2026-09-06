from enum import Enum


class CategoriaProduto(str, Enum):
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
