"""
Carrega as skills de skills/<agente>/<skill>/SKILL.md.

O prompt de um agente tem três camadas:

    compartilhado  persona, voz, contexto temporal, regras gerais, entrada e
                   envelope de saída — iguais para todo mundo
    preâmbulo      o que aquele domínio é e até onde vai, de prompt_<dominio>
    skill          o que fazer neste pedido: fluxo, regras e exemplos

Só a terceira muda de um pedido para o outro, e é a única que vem do Markdown.

A pasta define de quem é a skill. A intenção explícita seleciona a skill antes
da chamada ao modelo para evitar uma rodada extra e reduzir classificações
instáveis. O conteúdo da skill ainda recebe os fatos retornados pelas ferramentas.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .contexto_conversa import pedido_evento_composto
from .prompts.prompt_base import (
    ENTRADA_PADRAO,
    ENVELOPE_SAIDA,
    REGRAS_GERAIS,
    SYSTEM_PROMPT_AGENTE,
    TEMPORAL_CONTEXT,
    USO_DE_FERRAMENTAS,
)

PASTA = Path(__file__).resolve().parents[2] / "skills"

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    nome: str
    agente: str
    titulo: str
    descricao: str
    dominio: str
    ferramentas: tuple[str, ...]
    corpo: str

    def prompt(self, preambulo: str = "") -> str:
        camadas = [
            SYSTEM_PROMPT_AGENTE,
            TEMPORAL_CONTEXT,
            REGRAS_GERAIS,
            ENTRADA_PADRAO,
            USO_DE_FERRAMENTAS,
        ]

        if preambulo:
            camadas.append(preambulo.strip())

        camadas += [self.corpo, ENVELOPE_SAIDA]

        separador = "\n" * 3

        return separador.join(camadas)


def _valor(frontmatter: str, chave: str) -> str:
    achado = re.search(rf"^\s*{chave}:\s*(.+)$", frontmatter, re.MULTILINE)

    return achado.group(1).strip() if achado else ""


def _lista(frontmatter: str, chave: str) -> tuple[str, ...]:
    bruto = _valor(frontmatter, chave).strip("[]")

    return tuple(x.strip() for x in bruto.split(",") if x.strip())


def _ler(caminho: Path) -> Skill:
    texto = caminho.read_text(encoding="utf-8")
    cabecalho = _FRONTMATTER.match(texto)

    if cabecalho is None:
        raise ValueError(f"SKILL.md sem frontmatter em {caminho.parent}")

    frontmatter = cabecalho.group(1)

    return Skill(
        nome=caminho.parent.name,
        agente=caminho.parent.parent.name,
        titulo=_valor(frontmatter, "name"),
        descricao=_valor(frontmatter, "description"),
        dominio=_valor(frontmatter, "dominio"),
        ferramentas=_lista(frontmatter, "ferramentas"),
        corpo=texto[cabecalho.end():].strip(),
    )


def carregar() -> dict[str, Skill]:
    if not PASTA.is_dir():
        return {}

    return {s.nome: s for s in (_ler(p) for p in sorted(PASTA.glob("*/*/SKILL.md")))}


SKILLS: dict[str, Skill] = carregar()


def do_agente(agente: str) -> tuple[Skill, ...]:
    return tuple(s for s in SKILLS.values() if s.agente == agente)


def _normalizar_pedido(texto: str) -> str:
    return "".join(
        caractere for caractere in unicodedata.normalize("NFKD", (texto or "").casefold())
        if not unicodedata.combining(caractere)
    )


def classificar_modo_estoque(pedido: str) -> str:
    """Classifica se o estoque é requisito, contexto ou deve ser ignorado."""
    texto = _normalizar_pedido(pedido)

    # A negação precisa mencionar o estoque: "sem leite" ou "sem carne" é
    # uma restrição culinária, não um pedido para ignorar o inventário.
    excluir_estoque = any((
        re.search(r"\bsem\s+o\s+que\s+(?:eu\s+)?(?:tenho|tem|tenha)\b.*\bestoque\b", texto),
        re.search(r"\bsem\s+(?:os?\s+)?(?:itens|produtos|ingredientes)\s+(?:do|no)\s+(?:meu\s+)?estoque\b", texto),
        re.search(r"\bsem\s+(?:usar|utilizar|considerar|consultar|aproveitar)\s+(?:o\s+)?(?:meu\s+)?estoque\b", texto),
        re.search(r"\b(?:nao|nunca)\s+(?:use|consider(?:e|ar)|consulte|aproveite)\s+(?:o\s+)?(?:meu\s+)?estoque\b", texto),
        re.search(r"\bignore\s+(?:o\s+)?(?:meu\s+)?estoque\b", texto),
        re.search(r"\bignor(?:e|a|ar|ando)\s+(?:o\s+)?(?:meu\s+)?estoque\b", texto),
    ))
    if excluir_estoque:
        return "ignorar"

    exigir_estoque = re.search(
        r"\bcom\s+(?:o\s+que\s+(?:eu\s+)?(?:tenho|tem|ha)\s+(?:no\s+)?estoque|"
        r"(?:os?\s+)?(?:itens|ingredientes|produtos|alimentos)\s+do\s+(?:meu\s+)?estoque|"
        r"(?:os?\s+)?alimentos\s+que\s+(?:eu\s+)?(?:tenho|tem)\s+(?:no\s+)?estoque)|"
        r"\b(?:usando|aproveitando)\s+(?:o\s+que\s+(?:eu\s+)?(?:tenho|tem|ha)\s+(?:no\s+)?estoque|"
        r"(?:os?\s+)?(?:itens|ingredientes|produtos|alimentos)\s+(?:do\s+)?(?:meu\s+)?estoque|"
        r"(?:os?\s+)?alimentos\s+que\s+(?:eu\s+)?(?:tenho|tem)\s+(?:no\s+)?estoque)|"
        r"\bcom\s+o\s+que\s+(?:eu\s+)?tenho\s+em\s+casa\b",
        texto,
    )
    return "exigir" if exigir_estoque else "considerar"


def escolher_skill(agente: str, pedido: str, contexto_tipo: str | None = None) -> tuple[str, str]:
    """Roteia intenções claras sem uma chamada de modelo; retorna skill e motivo."""
    texto = _normalizar_pedido(pedido)

    if agente == "receitas":
        if classificar_modo_estoque(pedido) == "ignorar":
            return "receita-sem-estoque", "pedido explícito para não usar o estoque"
        salvar_ou_listar = re.search(
            r"\b(salv(e|ar)|guard(e|ar)|minhas receitas|receitas salvas|receita salva)\b", texto)
        adaptar = re.search(
            r"\b(troc(ar|a)|substitu(ir|a)|adapt(ar|e)|mude|alter(e|ar)|"
            r"complet(ar|e|a)|verific(ar|e)|avali(ar|e)|corrig(ir|a)|"
            r"sem\s+[\w-]+|nao gosto|alerg\w*|intoler\w*|restric\w*|dieta|"
            r"vegan[oa]s?|vegetarian[oa]s?|plant.?based)\b", texto)
        recuperar = re.search(
            r"\b(receita anterior|receita que voce (me )?(passou|deu)|"
            r"me (passa|da|de) de novo|recupere|recuperar|aquela receita)\b", texto)
        if salvar_ou_listar and not re.search(r"\b(troc|substitu|adapt|mude|altere)\w*\b", texto):
            return "receita-anterior", "pedido explícito de salvar ou consultar receitas"
        if adaptar:
            return "receita-com-restricao", "restrição ou adaptação culinária explícita"
        if recuperar:
            return "receita-anterior", "referência explícita a uma receita anterior"
        if contexto_tipo == "evento" or re.search(
                r"\b(evento|churrasco|aniversario|festa|convidados|cardapio)\b", texto):
            return "receita-para-evento", "receita vinculada a evento"
        return "receita-do-estoque", "geração nova; skill padrão baseada no objetivo e no estoque"

    if agente == "estoque":
        if re.search(r"\b(venc|validade|expir|perto de vencer)\w*\b", texto):
            return "estoque-validade", "consulta de validade"
        if re.search(r"\b(compr(ar|a)|repor|repor|reposicao|em falta|acabando|preciso de compra)\b", texto):
            return "estoque-compras", "intenção de compra ou reposição"
        if re.search(r"\b(revis(ar|ao)|atualiz(ar|acao) o estoque|consumi|joguei fora|descartei|dei baixa)\b", texto):
            return "estoque-atualizacao-guiada", "revisão ou baixa declarada"
        return "estoque-consultar", "consulta de estoque; padrão somente leitura"

    if agente == "eventos":
        if pedido_evento_composto(pedido):
            return "evento-criar-completo", "pedido composto: evento, receita salva e lista de compras"
        if re.search(r"\b(lista|listas)\b", texto):
            if re.search(r"\b(marcar|marque|comprad[oa]|renome|adicion|remov|tirar|progresso|como esta|status)\w*\b", texto):
                return "lista-gerenciar", "consulta ou alteração de lista existente"
            if re.search(r"\b(nova|crie|criar|monte|montar|gere|gerar|faca|fazer|lista para|lista do)\b", texto):
                return "lista-montar", "pedido para criar uma lista"
            return "lista-gerenciar", "consulta de lista; padrão somente leitura"
        evento_mencionado = contexto_tipo == "evento" or bool(re.search(
            r"\b(evento|churrasco|aniversario|festa|jantar|reuniao|convidados)\b", texto))
        if evento_mencionado and re.search(
                r"\b(receita|receitas|cardapio|menu|prato|adicion|remov|vincul|associad)\w*\b", texto):
            return "evento-receitas", "cardápio ou relação de receitas de evento"
        if re.search(r"\b(vou fazer|vamos fazer|vou organizar|planej|cri(?:e|a|ar)\s+(?:um\s+)?evento|"
                     r"novo evento|marque um evento|organizar\s+(?:um\s+)?(?:evento|festa)|"
                     r"organize\s+(?:uma\s+)?festa)\w*\b", texto):
            return "evento-criar", "planejamento de um evento novo"
        return "evento-gerenciar", "consulta ou gestão de evento existente; padrão sem criação"

    disponiveis = do_agente(agente)
    return (disponiveis[0].nome if disponiveis else ""), "skill padrão do domínio"


def catalogo(agente: str) -> str:
    """Nome e gatilho das skills de um agente, para ele escolher a sua."""

    return "\n".join(f"- {s.nome}: {s.descricao}" for s in do_agente(agente))
