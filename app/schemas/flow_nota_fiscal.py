import json
from datetime import date, timedelta
from decimal import Decimal

from langchain_core.messages import HumanMessage

from app.core.agents import nota_fiscal_app
from app.model.dto.nota_fiscal_request import NotaFiscalRequest
from app.model.dto.nota_fiscal_response import NotaFiscalResponse, ItemNotaFiscal
from app.model.dto.nota_fiscal_confirmacao_request import NotaFiscalConfirmacaoRequest
from app.model.dto.nota_fiscal_confirmacao_response import (
    NotaFiscalConfirmacaoResponse,
    ItemConfirmadoResponse,
)
from app.model.pgsql.pantry_item import Pantry_Item
from app.observability.tracing import generate_trace_id, span
from app.repository.pgsql.category import CategoryRepository
from app.repository.pgsql.config import SessionLocal
from app.repository.pgsql.food import FoodRepository
from app.repository.pgsql.stock import StockRepository


def extrair_itens_nota_fiscal(imagem_base64: str) -> NotaFiscalResponse:
    trace_id = generate_trace_id()

    with span(trace_id, "leitor_nota_fiscal"):
        url_imagem = (
            imagem_base64
            if imagem_base64.startswith("data:")
            else f"data:image/jpeg;base64,{imagem_base64}"
        )
        imagem = {
            "type": "image_url",
            "image_url": {"url": url_imagem},
        }

        resposta = nota_fiscal_app.invoke(
            {
                "messages": [
                    HumanMessage(content=[imagem]),
                ]
            },
            config={
                "metadata": {"trace_id": trace_id},
            },
        )

        mensagens_saida = resposta.get("messages", [])

        if not mensagens_saida:
            return NotaFiscalResponse(itens=[])

        conteudo_resposta = mensagens_saida[-1].content

        try:
            inicio = conteudo_resposta.find("{")
            fim = conteudo_resposta.rfind("}") + 1
            json_texto = conteudo_resposta[inicio:fim]
            dados = json.loads(json_texto)
        except (ValueError, json.JSONDecodeError):
            dados = {"itens": []}

        itens = []
        for item in dados.get("itens", []):
            marca_raw = item.get("marca")
            marca = str(marca_raw).strip() if marca_raw and str(marca_raw).strip() else None

            itens.append(
                ItemNotaFiscal(
                    marca=marca,
                    nome=str(item.get("nome", "") or "").strip(),
                    categoria=str(item.get("categoria", "Outros") or "Outros").strip(),
                    quantidade=int(item.get("quantidade", 1) or 1),
                    preco_unitario=item.get("preco_unitario"),
                    preco_total=item.get("preco_total"),
                )
            )

        return NotaFiscalResponse(itens=itens)


def confirmar_e_salvar_itens_nota_fiscal(
    request: NotaFiscalConfirmacaoRequest,
) -> NotaFiscalConfirmacaoResponse:
    trace_id = generate_trace_id()

    with span(trace_id, "confirmar_nota_fiscal"):
        itens_salvos = []

        with SessionLocal() as session:
            try:
                category_repo = CategoryRepository(session)
                food_repo = FoodRepository(session)

                for item in request.itens:
                    categoria = category_repo.get_or_create(item.categoria)
                    category_id = categoria.id if categoria else 1

                    peso = item.peso if item.peso is not None else Decimal("1.0")
                    unidade = item.unidade_medida or "unit"

                    food = food_repo.get_or_create(
                        name=item.nome,
                        category_id=category_id,
                        product_brand=item.marca,
                        package_quantity=peso,
                        unit_of_measure=unidade,
                    )

                    if not food:
                        continue

                    data_validade = item.data_validade or (date.today() + timedelta(days=30))

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
                            categoria=categoria.category_name if categoria else item.categoria,
                            quantidade=pantry_item.quantity,
                            data_validade=pantry_item.expiry_date,
                        )
                    )

                session.commit()

                return NotaFiscalConfirmacaoResponse(
                    sucesso=True,
                    mensagem=f"{len(itens_salvos)} itens salvos com sucesso no estoque.",
                    itens_salvos=itens_salvos,
                )

            except Exception as e:
                session.rollback()
                return NotaFiscalConfirmacaoResponse(
                    sucesso=False,
                    mensagem=f"Erro ao salvar itens no estoque: {str(e)}",
                    itens_salvos=[],
                )