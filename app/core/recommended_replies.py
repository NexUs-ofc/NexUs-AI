"""Sugestões locais com contagem lexical ponderada pela recência da sessão."""

import unicodedata

# Catálogo local. Cada frase é uma resposta provável em um fluxo conhecido.
# Não chama LLM, não consulta banco vetorial e não grava o contador.
RESPOSTAS_COMUNS = (
    "Sim",
    "Não",
    "Pode continuar",
    "Quero corrigir essa informação",
    "1 hora",
    "2 horas",
    "3 horas",
    "Hoje",
    "Amanhã",
    "No próximo sábado",
    "Às 12h",
    "Às 14h",
    "Às 19h",
    "Para 2 pessoas",
    "Para 4 pessoas",
    "Para 6 pessoas",
    "Na minha casa",
    "No endereço cadastrado",
    "Em outro endereço",
    "Sim, acabou",
    "Ainda tenho esse produto",
    "Consumi parcialmente",
    "Salve essa receita",
    "Monte uma lista de compras",
    "Faça outra receita",
    "Adapte para 2 porções",
    "Adapte para 4 porções",
    "O que está perto de vencer?",
    "O que está em falta no estoque?",
    "Marque os itens que já comprei",
    "Me mostre uma receita com meu estoque",
    "Veja meus próximos eventos",
)

_GRUPOS_DE_RESPOSTA = (
    ("duracao", ("duracao", "quantas horas", "quanto tempo"), (5, 6, 7)),
    ("pessoas", ("quantas pessoas", "numero de pessoas", "porcoes"), (14, 15, 16)),
    ("local", ("endereco", "onde sera", "onde vai ser", "local do evento"), (17, 18, 19)),
    ("data", ("que dia", "qual data", "data do evento", "quando sera"), (8, 9, 10)),
    ("horario", ("que horario", "qual horario", "que horas", "horario do evento"), (11, 12, 13)),
    ("consumo", ("acabou", "consumiu", "ainda tem", "jogou fora"), (20, 21, 22)),
    ("confirmacao", (
        "quer que eu", "gostaria de", "deseja que", "devo ",
        "posso completar", "posso salvar", "posso criar", "posso continuar",
        "posso atualizar", "pode confirmar", "confirma?",
    ), (1, 2, 3)),
)

_SINAIS_POR_RESPOSTA = {
    23: ("receita", "salvar", "salve", "ingredientes", "preparo"),
    24: ("para comprar", "falta comprar", "faltante", "comprar", "ingredientes faltantes"),
    25: ("receita", "prato", "sugira", "preparar"),
    26: ("porcoes", "rende", "servir"),
    27: ("porcoes", "rende", "servir"),
    28: ("estoque", "validade", "venc", "acaba"),
    29: ("estoque", "falta", "repor", "acabando", "minimo"),
    30: ("lista de compras", "lista", "itens", "comprados"),
    31: ("estoque", "tenho", "possui", "produtos", "itens"),
    32: ("evento", "agendado", "horario", "data", "local"),
}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    return " ".join("".join(char for char in texto if not unicodedata.combining(char)).split())


def _contem(texto: str, *termos: str) -> bool:
    return any(termo in texto for termo in termos)


def _contexto_pesado(
    historico: list[dict] | None,
    mensagem_usuario: str,
    resposta: str,
) -> list[tuple[str, float]]:
    """Conta sinais por turno: resposta atual > mensagem atual > histórico decaído."""
    segmentos = [(resposta, 4.0), (mensagem_usuario, 5.0)]
    mensagens = [
        str(item.get("content") or "")
        for item in (historico or [])[-12:]
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"}
    ]
    total = len(mensagens)
    for indice, conteudo in enumerate(mensagens):
        distancia = total - indice
        # O histórico ainda conta como frequência, mas cada turno mais antigo
        # contribui menos que o anterior.
        peso = 1.8 * (0.58 ** (distancia / 2))
        segmentos.append((conteudo, peso))
    return [(_normalizar(texto), peso) for texto, peso in segmentos if texto]


def _pontuar_resposta(
    indice: int,
    segmentos: list[tuple[str, float]],
    rota: str,
) -> float:
    sinais = _SINAIS_POR_RESPOSTA.get(indice, ())
    score = 1.0 if rota else 0.0
    for texto, peso in segmentos:
        encontrados = sum(1 for sinal in sinais if sinal in texto)
        if encontrados:
            score += peso * min(encontrados, 2) / 2
    return score


def prever_respostas_recomendadas(
    mensagem_usuario: str,
    resposta: str,
    rota: str = "",
    envelope: dict | None = None,
    historico: list[dict] | None = None,
) -> list[str] | None:
    """Ranqueia até três frases pelo contexto atual e a frequência recente."""
    envelope = envelope if isinstance(envelope, dict) else {}
    resposta_n = _normalizar(resposta or "")
    mensagem_n = _normalizar(mensagem_usuario or "")
    rota_n = _normalizar(rota or "")

    if not resposta_n or _contem(
        resposta_n,
        "nao consegui concluir todas as etapas",
        "temporariamente indisponivel",
        "nao consegui gerar uma receita completa",
        "nao consegui montar uma receita completa",
    ):
        return None

    segmentos = _contexto_pesado(historico, mensagem_usuario, resposta)
    texto_pergunta = _normalizar(str(envelope.get("esclarecer") or resposta))
    pergunta_pendente = bool(envelope.get("esclarecer")) or "?" in resposta

    if pergunta_pendente:
        grupo = next(
            (indices for _nome, sinais, indices in _GRUPOS_DE_RESPOSTA
             if any(sinal in texto_pergunta for sinal in sinais)),
            None,
        )
        if grupo:
            ordenadas = sorted(
                grupo,
                key=lambda indice: (
                    _pontuar_resposta(indice, segmentos, rota_n), -indice,
                ),
                reverse=True,
            )
            return [RESPOSTAS_COMUNS[indice - 1] for indice in ordenadas[:3]]

    receita = envelope.get("receita")
    elegiveis: list[int] = []
    if rota_n == "receitas" and isinstance(receita, dict):
        faltantes = receita.get("ingredientes_faltantes") or receita.get("missing_ingredients") or []
        ja_salva = _contem(resposta_n, "receita foi salva", "receita salva", "salvei a receita")
        if faltantes:
            elegiveis.append(24)
        if not ja_salva:
            elegiveis.append(23)
        porcoes = receita.get("porcoes") or receita.get("serving_size")
        try:
            porcoes = int(porcoes) if porcoes is not None else None
        except (TypeError, ValueError):
            porcoes = None
        if porcoes and porcoes != 2:
            elegiveis.append(26)
        if porcoes and porcoes != 4:
            elegiveis.append(27)
        elegiveis.append(25)

    elif rota_n == "estoque":
        if _contem(resposta_n, "estoque", "produto", "unidade", "voce tem", "voce possui"):
            elegiveis.extend((28, 29, 31))
        elif _contem(resposta_n, "vence", "vencimento", "validade"):
            elegiveis.extend((29, 31))

    elif rota_n == "eventos":
        criou_evento = _contem(resposta_n, "criei o evento", "evento criado", "agendei o evento")
        tem_lista = _contem(resposta_n, "lista de compras") or isinstance(envelope.get("lista"), dict)
        tem_receita = isinstance(receita, dict) or _contem(resposta_n, "receita")
        if criou_evento:
            elegiveis.append(32)
        if tem_receita and not _contem(resposta_n, "salvei a receita", "receita salva"):
            elegiveis.append(23)
        if not tem_lista:
            elegiveis.append(24)
        else:
            elegiveis.append(30)

    elif _contem(mensagem_n, "lista de compras"):
        elegiveis.append(30)

    if not elegiveis:
        return None

    scores = {
        indice: _pontuar_resposta(indice, segmentos, rota_n)
        for indice in set(elegiveis)
    }
    if rota_n == "receitas" and isinstance(receita, dict):
        porcoes = receita.get("porcoes") or receita.get("serving_size")
        try:
            porcoes = int(porcoes) if porcoes is not None else None
        except (TypeError, ValueError):
            porcoes = None
        if porcoes == 2 and 27 in scores:
            scores[27] += 2.0
        elif porcoes == 4 and 26 in scores:
            scores[26] += 2.0
        if (receita.get("ingredientes_faltantes") or receita.get("missing_ingredients")) and 24 in scores:
            scores[24] += 2.5
    elif rota_n == "estoque":
        # Termos claros da última mensagem vencem a frequência antiga da sessão.
        if _contem(mensagem_n, "venc", "validade", "prazo") and 28 in scores:
            scores[28] += 4.0
        if _contem(mensagem_n, "em falta", "repor", "acabando", "quantidade minima") and 29 in scores:
            scores[29] += 4.0

    ordenadas = sorted(scores, key=lambda indice: (-scores[indice], indice))
    return [RESPOSTAS_COMUNS[indice - 1] for indice in ordenadas[:3]] or None
