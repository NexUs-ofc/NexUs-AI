"""
Workflow do leitor de notas fiscais.

Fluxo em duas etapas, de propósito:
    1. extrair_itens_nota_fiscal  -> agente multimodal lê a imagem e devolve
       os itens (nada é gravado).
    2. confirmar_e_salvar_itens_nota_fiscal -> o app envia os itens já
       revisados pelo usuário e só então eles entram no estoque.

Assim nenhuma alucinação do modelo de visão vai direto para o banco.
"""

import base64
import binascii
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from langchain_core.messages import HumanMessage
from langsmith import traceable, tracing_context
from sqlalchemy.exc import SQLAlchemyError

from app.controller.config import logging
from app.core.agents import nota_fiscal_app
from app.model.dto.nota_fiscal_confirmacao_request import NotaFiscalConfirmacaoRequest
from app.model.dto.nota_fiscal_confirmacao_response import (
    ItemConfirmadoResponse,
    NotaFiscalConfirmacaoResponse,
)
from app.model.dto.nota_fiscal_response import NotaFiscalExtraida, NotaFiscalResponse
from app.model.pgsql.pantry_item import Pantry_Item
from app.observability.cost import extrair_tokens
from app.observability.tracing import generate_trace_id, span
from app.repository.mongodb.metrics import MetricsRepository
from app.repository.pgsql.category import CategoryRepository
from app.repository.pgsql.config import SessionLocal
from app.repository.pgsql.food import FoodRepository

logger = logging.getLogger(__name__)

# Validade usada quando nem a nota nem o usuário informam uma data.
# O item volta marcado com validade_estimada=True para o app sinalizar.
VALIDADE_PADRAO_DIAS = 30

_ASSINATURAS_IMAGEM = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),
)
_MIMES_ACEITOS = {"image/jpeg", "image/png", "image/webp"}


class ImagemInvalidaError(ValueError):
    """Imagem ausente, corrompida ou em formato não suportado."""


class LeituraNotaFiscalError(RuntimeError):
    """O modelo não conseguiu devolver uma leitura estruturada."""


def _normalizar_imagem(imagem_base64: str) -> str:
    """
    Valida o base64 e devolve uma data URL com o MIME correto.

    Antes o código assumia sempre image/jpeg, o que quebra PNG/WEBP enviados
    pelo app. Aqui o MIME vem do cabeçalho data: ou dos magic bytes.
    """

    conteudo = imagem_base64.strip()
    mime = None

    if conteudo.startswith("data:"):
        cabecalho, _, conteudo = conteudo.partition(",")
        mime = cabecalho[5:].split(";")[0].lower() or None

    try:
        bruto = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError) as erro:
        raise ImagemInvalidaError("imagem_base64 não é um base64 válido") from erro

    if mime is None:
        mime = next(
            (tipo for assinatura, tipo in _ASSINATURAS_IMAGEM if bruto.startswith(assinatura)),
            None,
        )

    if mime not in _MIMES_ACEITOS:
        raise ImagemInvalidaError(
            f"Formato de imagem não suportado ({mime or 'desconhecido'}). "
            "Envie JPEG, PNG ou WEBP."
        )

    return f"data:{mime};base64,{conteudo}"


def _entrada_sem_imagem(inputs: dict) -> dict:
    # A foto da nota costuma ter CPF/nome do consumidor: nunca vai para o trace.
    return {"imagem": "[omitida]"}


@traceable(name="leitor_nota_fiscal", run_type="chain", process_inputs=_entrada_sem_imagem)
def extrair_itens_nota_fiscal(imagem_base64: str) -> NotaFiscalResponse:
    trace_id = generate_trace_id()
    url_imagem = _normalizar_imagem(imagem_base64)

    started_at = datetime.now(timezone.utc)
    input_tokens = output_tokens = 0
    erro = True

    try:
        with span(trace_id, "leitor_nota_fiscal"), tracing_context(enabled=False):
            resultado = nota_fiscal_app.invoke(
                {
                    "messages": [
                        HumanMessage(
                            content=[
                                {
                                    "type": "text",
                                    "text": "Extraia os itens desta nota fiscal.",
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": url_imagem},
                                },
                            ]
                        ),
                    ]
                },
                config={"metadata": {"trace_id": trace_id}},
            )

        for msg in resultado.get("messages", []):
            tokens_in, tokens_out = extrair_tokens(msg)
            input_tokens += tokens_in
            output_tokens += tokens_out

        extraida = resultado.get("structured_response")

        if not isinstance(extraida, NotaFiscalExtraida):
            raise LeituraNotaFiscalError("O agente não devolveu uma leitura estruturada")

        erro = False

        logger.info(
            "nota fiscal lida",
            extra={
                "trace_id": trace_id,
                "stage": "nota_fiscal",
                "itens": len(extraida.itens),
                "legivel": extraida.legivel,
            },
        )

        return NotaFiscalResponse(
            itens=extraida.itens,
            legivel=extraida.legivel,
            trace_id=trace_id,
        )

    finally:
        finished_at = datetime.now(timezone.utc)

        MetricsRepository.save_request_metric(
            trace_id=trace_id,
            route="nota_fiscal",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=(finished_at - started_at).total_seconds() * 1000,
            tool_calls=0,
            error=erro,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            # estimate_cost_usd usa preço do Groq; Gemini tem outra tabela.
            cost_usd=0.0,
        )


def confirmar_e_salvar_itens_nota_fiscal(
    request: NotaFiscalConfirmacaoRequest,
) -> NotaFiscalConfirmacaoResponse:
    """
    Grava no estoque os itens confirmados pelo usuário.

    Tudo ou nada: roda numa única transação; se qualquer item falhar, nada é
    gravado (antes itens com erro eram pulados em silêncio).
    """

    trace_id = generate_trace_id()
    itens_salvos: list[ItemConfirmadoResponse] = []

    with span(trace_id, "confirmar_nota_fiscal"), SessionLocal() as session:
        try:
            category_repo = CategoryRepository(session)
            food_repo = FoodRepository(session)

            for item in request.itens:
                categoria = category_repo.get_or_create(item.categoria)

                food = food_repo.get_or_create(
                    name=item.nome,
                    category_id=categoria.id,
                    product_brand=item.marca,
                    package_quantity=Decimal(str(item.peso)) if item.peso is not None else None,
                    unit_of_measure=item.unidade_medida,
                )

                validade_estimada = item.data_validade is None
                data_validade = item.data_validade or (
                    datetime.now(timezone.utc).astimezone().date()
                    + timedelta(days=VALIDADE_PADRAO_DIAS)
                )

                pantry_item = Pantry_Item(
                    food_id=food.id,
                    profile_id=request.household_account_id,
                    quantity=item.quantidade,
                    expiry_date=data_validade,
                )
                session.add(pantry_item)
                session.flush()

                itens_salvos.append(
                    ItemConfirmadoResponse(
                        pantry_item_id=pantry_item.id,
                        food_id=food.id,
                        nome=food.name,
                        marca=food.product_brand,
                        categoria=categoria.category_name,
                        quantidade=pantry_item.quantity,
                        data_validade=pantry_item.expiry_date,
                        validade_estimada=validade_estimada,
                    )
                )

            session.commit()

        except SQLAlchemyError:
            session.rollback()

            logger.exception(
                "Erro ao salvar itens da nota fiscal",
                extra={"trace_id": trace_id, "stage": "nota_fiscal"},
            )

            # Mensagem genérica: detalhes do banco ficam só no log.
            return NotaFiscalConfirmacaoResponse(
                sucesso=False,
                mensagem="Não foi possível salvar os itens no estoque. Tente novamente.",
                itens_salvos=[],
            )

    return NotaFiscalConfirmacaoResponse(
        sucesso=True,
        mensagem=f"{len(itens_salvos)} itens salvos com sucesso no estoque.",
        itens_salvos=itens_salvos,
    )
