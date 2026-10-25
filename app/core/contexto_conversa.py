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
            if isinstance(assunto, dict) and assunto.get("tipo") in {"evento", "receita"}:
                return deepcopy(assunto)
            if isinstance(turno.get("receita"), dict):
                return {"tipo": "receita", "receita": deepcopy(turno["receita"])}
        elif turno.get("role") == "user" and menciona_evento(str(turno.get("content", ""))):
            # Sessões anteriores à introdução do metadado: uma conversa nova
            # sobre evento já impede recuperar uma receita avulsa mais antiga.
            return {"tipo": "evento", "pedido": turno["content"]}
    return None


def resolver_assunto(historico: list[dict], mensagem: str) -> dict | None:
    atual = assunto_recente(historico)
    texto = normalizar(mensagem)
    if menciona_evento(mensagem):
        if atual and atual["tipo"] == "evento":
            return atual
        return {"tipo": "evento", "pedido": mensagem}
    # Referência explícita pode voltar a uma receita anterior, mas um pedido
    # genérico nunca escolhe a receita antiga por ela ser a última estruturada.
    for turno in reversed(historico or []):
        receita = turno.get("receita") if turno.get("role") == "assistant" else None
        if isinstance(receita, dict):
            titulo = str(receita.get("titulo") or receita.get("title") or "").strip()
            if titulo and re.search(r"(?<!\w)" + re.escape(normalizar(titulo)) + r"(?!\w)", texto):
                return {"tipo": "receita", "receita": deepcopy(receita)}
    return atual


def assunto_do_turno(historico: list[dict], mensagem: str, envelope: dict,
                     receita: dict | None) -> dict | None:
    atual = resolver_assunto(historico, mensagem)
    intencao = normalizar(str(envelope.get("intencao") or ""))
    evento = envelope.get("evento")
    de_evento = menciona_evento(mensagem) or "evento" in intencao or isinstance(evento, dict)
    if receita and not de_evento:
        return {"tipo": "receita", "receita": deepcopy(receita)}
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
