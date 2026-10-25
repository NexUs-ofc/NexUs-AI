"""Validações de dados de domínio, independentes dos modelos de linguagem."""

import re
import unicodedata


def validar_titulo(titulo: str) -> str:
    titulo = titulo.strip()
    if not titulo or re.search(r"\[(?:PII_|(?:TELEFONE|CPF|EMAIL) OMITIDO)", titulo, re.IGNORECASE):
        raise ValueError("Informe um título sem dados pessoais ou marcadores de privacidade.")
    return titulo


def _normalizar(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto.casefold())
                   if not unicodedata.combining(c))


def ingredientes_basicos_ausentes(ingredientes: list[dict], instrucoes: str) -> list[str]:
    """Detecta omissões comuns; não inventa quantidades nem valida toda a culinária."""
    nomes = " ".join(str(i.get("name") or i.get("nome") or i.get("ingrediente") or "")
                     for i in ingredientes if isinstance(i, dict))
    nomes, preparo = _normalizar(nomes), _normalizar(instrucoes)
    # Mencionar uma restrição no preparo não significa usar o ingrediente.
    preparo = re.sub(r"\bsem\s+(?:agua|sal|azeite|oleo|manteiga|acucar|leite)\b", "", preparo)
    preparo = re.sub(r"\bnao\s+(?:use|adicione|acrescente|coloque)\b[^.!?\n]*", "", preparo)
    basicos = {"água": r"\bagua\b", "sal": r"\bsal\b", "azeite": r"\bazeite\b",
               "óleo": r"\boleo\b", "manteiga": r"\bmanteiga\b", "açúcar": r"\bacucar\b",
               "leite": r"\bleite\b"}
    # Água para lavar utensílios/alimentos não é ingrediente. A checagem
    # aplica-se apenas a água explicitamente adicionada ao prato.
    agua_no_prato = bool(re.search(
        r"\b(?:adicione|acrescente|junte|despeje|coloque)\b[^.!?\n]*\bagua\b", preparo))
    return [nome for nome, padrao in basicos.items()
            if re.search(padrao, preparo) and not re.search(padrao, nomes)
            and (nome != "água" or agua_no_prato)]
