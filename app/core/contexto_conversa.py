"""Assunto ativo da sessão: receita avulsa e evento não são intercambiáveis."""

import re
import unicodedata
from copy import deepcopy


def normalizar(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto.casefold())
                   if not unicodedata.combining(c))


def menciona_evento(texto: str) -> bool:
    return bool(re.search(r"\b(?:evento|churrasco|festa|aniversario)\b", normalizar(texto)))


def pedido_lista_generico(texto: str) -> bool:
    texto = normalizar(texto).strip(" .!?\n")
    return bool(re.fullmatch(
        r"(?:sim[, ]+)?(?:agora[, ]+)?(?:pode\s+)?(?:me\s+)?"
        r"(?:monte|monta|montar|crie|cria|criar|gere|gerar|faca|faz|fazer)\s+"
        r"(?:(?:uma|a|minha)\s+)?lista(?:\s+de\s+compras)?(?:\s+por\s+favor)?", texto))


def assunto_recente(historico: list[dict]) -> dict | None:
    for turno in reversed(historico or []):
        if turno.get("role") == "assistant":
            assunto = turno.get("assunto")
            if isinstance(assunto, dict) and assunto.get("tipo") in {"evento", "receita", "receita_pendente"}:
                return deepcopy(assunto)
            if isinstance(turno.get("receita"), dict):
                return {"tipo": "receita", "receita": deepcopy(turno["receita"])}
        elif turno.get("role") == "user" and menciona_evento(str(turno.get("content", ""))):
            # Sessões anteriores à introdução do metadado: uma conversa nova
            # sobre evento já impede recuperar uma receita avulsa mais antiga.
            return {"tipo": "evento", "pedido": turno["content"]}
    return None


def _nova_receita(texto_normalizado: str) -> bool:
    if re.search(r"\b(receita anterior|receita que voce (me )?(passou|deu)|aquela receita|essa receita)\b",
                 texto_normalizado):
        return False
    return bool(re.search(
        r"\b(nova|outra) receita\b|\b(receita (de|com|para))\b|"
        r"\b(sugira|sugere|crie|criar|gere|gerar|faca|prepare) uma receita\b",
        texto_normalizado,
    ))


def _referencia_assunto(texto_normalizado: str, assunto: dict) -> bool:
    # Uma confirmação curta responde à pergunta de esclarecimento anterior.
    # Sem este elo, "sim" virava um assunto novo e a receita perdia os dados
    # que a pessoa já tinha informado.
    if assunto.get("tipo") == "receita_pendente" and re.fullmatch(
        r"(?:sim|s|isso|pode|claro|nao|não|n|ok|certo|\d+(?:[,.]\d+)?(?:\s+\w+)?)"
        r"[.!? ]*", texto_normalizado,
    ):
        return True
    if pedido_lista_generico(texto_normalizado):
        return True
    if assunto.get("tipo") == "evento" and re.search(
        r"\b(adie|adiar|reagende|reagendar|cancele|cancelar|atualize|atualizar|"
        r"altere|alterar|mude|mudar|remarque|remarcar)\b", texto_normalizado,
    ):
        return True
    evento = assunto.get("evento") or {}
    titulo = normalizar(str(evento.get("titulo") or evento.get("title") or ""))
    if titulo and re.search(r"(?<!\w)" + re.escape(titulo) + r"(?!\w)", texto_normalizado):
        return True
    return bool(re.search(
        r"\b(essa|esse|dessa|desse|anterior|mesma|mesmo|ela|dele|dela|isso|"
        r"restante|mantendo|mantenha|troque|substitua|adapte|complete|salve essa|"
        r"sem\s+[\w-]+|e se|e sem|lista dela|do evento|desse evento)\b",
        texto_normalizado,
    ))


def resolver_assunto(historico: list[dict], mensagem: str) -> dict | None:
    atual = assunto_recente(historico)
    texto = normalizar(mensagem)
    if menciona_evento(mensagem):
        if atual and atual["tipo"] == "evento" and _referencia_assunto(texto, atual):
            return atual
        return {"tipo": "evento", "pedido": mensagem}

    # Uma nova receita não deve receber contexto antigo por acidente.
    nova_receita = _nova_receita(texto)
    for turno in reversed(historico or []):
        receita = turno.get("receita") if turno.get("role") == "assistant" else None
        if isinstance(receita, dict):
            titulo = str(receita.get("titulo") or receita.get("title") or "").strip()
            if titulo and re.search(r"(?<!\w)" + re.escape(normalizar(titulo)) + r"(?!\w)", texto):
                return {"tipo": "receita", "receita": deepcopy(receita)}

    if nova_receita:
        return None
    if atual and _referencia_assunto(texto, atual):
        return atual
    # Alguns nós pedem o assunto sem haver uma mensagem nova (por exemplo,
    # formatação/testes); nesse caso não há risco de carregar contexto à resposta.
    if not mensagem and atual:
        return atual
    return None


def assunto_do_turno(historico: list[dict], mensagem: str, envelope: dict,
                     receita: dict | None) -> dict | None:
    atual = resolver_assunto(historico, mensagem)
    intencao = normalizar(str(envelope.get("intencao") or ""))
    evento = envelope.get("evento")
    de_evento = menciona_evento(mensagem) or "evento" in intencao or isinstance(evento, dict)
    if receita and not de_evento:
        return {"tipo": "receita", "receita": deepcopy(receita)}
    if (not de_evento and receita is None
            and re.search(r"\b(receita|cozinhar|cozinhe|preparar|prato)\b", normalizar(mensagem))
            and "receita" in intencao):
        pendente = {"tipo": "receita_pendente", "pedido": mensagem}
        candidata = envelope.get("receita")
        if isinstance(candidata, dict):
            pendente["receita"] = deepcopy(candidata)
        return pendente
    if de_evento:
        assunto = deepcopy(atual) if atual and atual["tipo"] == "evento" else {"tipo": "evento", "pedido": mensagem}
        if isinstance(evento, dict):
            anterior = assunto.get("evento") or {}
            old_id, new_id = anterior.get("_id") or anterior.get("id"), evento.get("_id") or evento.get("id")
            old_title = anterior.get("titulo") or anterior.get("title")
            new_title = evento.get("titulo") or evento.get("title")
            if ((old_id and new_id and str(old_id) != str(new_id)) or
                    (not (old_id and new_id) and old_title and new_title
                     and normalizar(old_title) != normalizar(new_title))):
                assunto = {"tipo": "evento", "pedido": mensagem}
            assunto["evento"] = deepcopy(evento)
        if receita:
            assunto["receita_evento"] = deepcopy(receita)
        # Guardar a declaração literal evita transformar uma alergia dos
        # convidados em preferência/restrição permanente do perfil.
        if re.search(r"alerg|intoler|restri", normalizar(mensagem)):
            declaracoes = assunto.setdefault("restricoes_declaradas", [])
            if mensagem not in declaracoes:
                declaracoes.append(mensagem)
        return assunto
    return atual
