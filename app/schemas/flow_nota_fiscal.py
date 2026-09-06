import json

from langchain_core.messages import HumanMessage

from app.core.agents import nota_fiscal_app
from app.model.dto.nota_fiscal_response import NotaFiscalResponse, ItemNotaFiscal
from app.observability.tracing import generate_trace_id, span


def extrair_itens_nota_fiscal(imagem_base64: str) -> NotaFiscalResponse:
    trace_id = generate_trace_id()

    with span(trace_id, "leitor_nota_fiscal"):
        imagem = {"type": "image_url", "image_url": f"data:image/jpeg;base64,{imagem_base64}"}

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

        itens = [
            ItemNotaFiscal(
                marca=str(item.get("marca", "") or ""),
                nome=str(item.get("nome", "") or ""),
                categoria=str(item.get("categoria", "") or ""),
                quantidade=int(item.get("quantidade", 1) or 1),
                preco_unitario=item.get("preco_unitario"),
                preco_total=item.get("preco_total"),
            )
            for item in dados.get("itens", [])
        ]

        return NotaFiscalResponse(itens=itens)
