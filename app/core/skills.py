"""
Carrega as skills de skills/<agente>/<skill>/SKILL.md.

O prompt de um agente tem três camadas:

    compartilhado  persona, voz, contexto temporal, regras gerais, entrada e
                   envelope de saída — iguais para todo mundo
    preâmbulo      o que aquele domínio é e até onde vai, de prompt_<dominio>
    skill          o que fazer neste pedido: fluxo, regras e exemplos

Só a terceira muda de um pedido para o outro, e é a única que vem do Markdown.

A pasta define de quem é a skill. Quem escolhe entre elas é o próprio agente,
não o roteador: a escolha costuma depender do que as ferramentas devolveram, e
só o agente tem isso na mão.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from .prompts.prompt_base import (
    ENTRADA_PADRAO,
    ENVELOPE_SAIDA,
    REGRAS_GERAIS,
    SYSTEM_PROMPT,
    TEMPORAL_CONTEXT,
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
        camadas = [SYSTEM_PROMPT, TEMPORAL_CONTEXT, REGRAS_GERAIS, ENTRADA_PADRAO]

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


def catalogo(agente: str) -> str:
    """Nome e gatilho das skills de um agente, para ele escolher a sua."""

    return "\n".join(f"- {s.nome}: {s.descricao}" for s in do_agente(agente))
