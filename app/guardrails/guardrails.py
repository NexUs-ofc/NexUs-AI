import re
import uuid
from app.core.llms import fast_llm


PII = [
    ("CPF",      r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"),
    ("TELEFONE", r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}"),
    ("EMAIL",    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
]


def _bloquear(motivo, mensagem):
    return {"bloqueado": True, "motivo": motivo, "mensagem": mensagem}


def _aprovado():
    return {"bloqueado": False, "motivo": "aprovado", "mensagem": ""}


def _saida_ok(conteudo):
    return {"bloqueado": False, "motivo": "saida_revisada", "conteudo": conteudo}


def anonimizar(texto):
    mapa = {}
    for tipo, padrao in PII:
        matches = re.findall(padrao, texto)
        for valor in matches:
            token = f"[PII_{tipo}_{uuid.uuid4().hex[:6]}]"
            mapa[token] = valor
            texto = texto.replace(valor, token, 1)
    return texto, mapa


def desanonimizar(texto, mapa):
    for token, valor in mapa.items():
        tipo = token.split("_")[1]
        texto = texto.replace(token, f"[{tipo} OMITIDO]")
    return texto


_PADROES_INJECAO = [
    r"ignore\s+(as\s+)?instru[çc][oõ]es",
    r"ignore\s+previous\s+instructions",
    r"forget\s+your\s+instructions",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(if\s+)?",
    r"pretend\s+(you\s+are|to\s+be)",
    r"jailbreak",
    r"dan\s+mode",
    r"modo\s+irrestrito",
    r"system\s*prompt",
    r"<\s*system\s*>",
    r"\[INST\]",
    r"###\s*instruction",
    r"override\s+(your\s+)?instructions",
    r"desconsider[ea]\s+(suas\s+)?instru[çc][oõ]es",
]


_KEYWORDS_DADOS_INTERNOS = [
    "prompt do sistema", "system prompt", "suas instruções",
    "your instructions", "chave de api", "api key",
    "senha do sistema", "token de acesso",
]


_PROMPT_CLASSIFICADOR = """\
Você é um classificador de segurança do Ceris.AI, um app de gestão de alimentos domésticos.
Classifique a mensagem em UMA categoria. Responda SOMENTE:

Se a mensagem contém tokens [PII_CPF_XXXXX] ou similares, e o conteúdo não é ilícito, classifique como APROVADO.

CATEGORIA: [categoria]
JUSTIFICATIVA: [uma linha]

Categorias:
APROVADO  - mensagem legítima sobre alimentos, estoque, receitas, eventos ou dúvidas do app
OFENSIVO  - xingamentos, assédio, discurso de ódio
PERIGOSO  - instruções que causam dano físico ou psicológico
ILICITO   - pedido de auxílio para atividades ilegais

Mensagem: {mensagem}
"""

_RESPOSTAS_BLOQUEIO = {
    "OFENSIVO": ("conteudo_ofensivo", "Por favor, mantenha um tom respeitoso para que eu possa te ajudar."),
    "PERIGOSO": ("pedido_perigoso", "Não posso ajudar com esse tipo de solicitação."),
    "ILICITO":  ("pedido_ilicito", "Não posso auxiliar com atividades ilegais."),
}


def checar_entrada(mensagem_anonimizada):
    for padrao in _PADROES_INJECAO:
        if re.search(padrao, mensagem_anonimizada, re.IGNORECASE):
            return _bloquear("prompt_injection", "Não consigo processar essa solicitação.")

    texto_lower = mensagem_anonimizada.lower()
    for kw in _KEYWORDS_DADOS_INTERNOS:
        if kw in texto_lower:
            return _bloquear("acesso_dados_internos", "Não tenho como compartilhar informações internas do sistema.")

    resposta = fast_llm.invoke(
        _PROMPT_CLASSIFICADOR.format(mensagem=mensagem_anonimizada)
    ).content

    categoria = "APROVADO"
    for linha in resposta.splitlines():
        if linha.strip().upper().startswith("CATEGORIA:"):
            categoria = linha.split(":", 1)[1].strip().upper()
            break

    if categoria in _RESPOSTAS_BLOQUEIO:
        motivo, msg = _RESPOSTAS_BLOQUEIO[categoria]
        return _bloquear(motivo, msg)

    return _aprovado()


_PROMPT_SAIDA = """\
Você é um revisor de qualidade do Ceris.AI.
Revise a resposta e corrija SOMENTE se ela:
- Afirmar segurança alimentar de um produto sem ressalva
- Dar conselho médico ou nutricional sem disclaimer
- Garantir validade ou frescor de um alimento sem verificação
- Conter informação em outro idioma que não português brasileiro

Se estiver adequada, repita sem alterações.

Responda SOMENTE:
STATUS: APROVADO ou CORRIGIDO
RESPOSTA:
[texto final]

Resposta para revisar:
{resposta}
"""


def checar_saida(resposta, mapa_pii):
    for tipo, padrao in PII:
        resposta = re.sub(padrao, f"[{tipo} OMITIDO]", resposta)

    resposta = desanonimizar(resposta, mapa_pii)

    saida = fast_llm.invoke(
        _PROMPT_SAIDA.format(resposta=resposta)
    ).content.strip()

    if "RESPOSTA:" in saida:
        texto = saida.split("RESPOSTA:", 1)[1].strip()
        if texto:
            resposta = texto

    return _saida_ok(resposta)
