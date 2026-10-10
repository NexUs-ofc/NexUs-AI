"""
O que não pode derrubar o grafo.

Cada teste aqui nasceu de um jeito real de quebrar o sistema: rota que o
roteador inventa, histórico que cresce sem fim, juiz devolvendo para uma rota
que não existe, resposta do juiz fora de formato.

Nenhum deles chama LLM, banco ou rede.
"""

import pytest

from app.repository.mongodb.metrics import _percentil
from app.schemas.flow import (
    CONFIANCA_PARA_DEVOLVER,
    LIMITE_DEVOLUCOES,
    ROTAS,
    TURNOS_PARA_O_AGENTE,
    _formatar_conversa,
    _formatar_evidencias,
    _ler_veredito,
    _ler_veredito_completo,
    _normalizar_rota,
    _ultimos_turnos,
    decidir_pos_juiz,
    decidir_rota,
)

# --------------------------------------------------------------- rota

@pytest.mark.parametrize("rota", ROTAS)
def test_rota_valida_passa_intacta(rota):
    assert _normalizar_rota(rota) == rota


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("ESTOQUE", "estoque"),
        ("  receitas  ", "receitas"),
        ("estoque.", "estoque"),
        ("Rota: eventos", "eventos"),
        ("A rota escolhida e faq", "faq"),
    ],
)
def test_rota_suja_e_normalizada(bruto, esperado):
    assert _normalizar_rota(bruto) == esperado


@pytest.mark.parametrize("bruto", ["", "   ", None, "qualquer coisa", "{}", "42"])
def test_rota_irreconhecivel_cai_em_fallback(bruto):
    assert _normalizar_rota(bruto) == "fallback"


def test_toda_rota_normalizada_e_atendida_pelo_grafo():
    """O destino tem que existir no mapa de arestas, senão o grafo levanta erro."""

    for bruto in ["estoque", "LIXO", "", "Rota: receitas", None]:
        assert _normalizar_rota(bruto) in ROTAS


def test_decidir_rota_le_do_state():
    assert decidir_rota({"rota": "faq"}) == "faq"


# ------------------------------------------------------------ histórico

def test_historico_vazio_nao_quebra():
    assert _ultimos_turnos([], 5) == []
    assert _ultimos_turnos(None, 5) == []


def test_historico_menor_que_o_teto_vem_inteiro():
    turnos = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]

    assert _ultimos_turnos(turnos, 10) == turnos


def test_historico_longo_e_cortado_pelos_ultimos():
    turnos = [{"role": "user", "content": str(i)} for i in range(50)]

    recorte = _ultimos_turnos(turnos, TURNOS_PARA_O_AGENTE)

    assert len(recorte) == TURNOS_PARA_O_AGENTE
    assert recorte[-1]["content"] == "49"


def test_conversa_do_juiz_tem_teto_e_rotulo_legivel():
    turnos = [{"role": "user", "content": "x" * 5000}] * 20

    bloco = _formatar_conversa(turnos)

    assert "usuário" in bloco
    assert len(bloco) < 20 * 5000


def test_conversa_vazia_e_anunciada():
    assert _formatar_conversa([]) == "primeira mensagem da conversa"


# ----------------------------------------------------------------- juiz

def test_juiz_devolve_so_para_rota_com_agente():
    for rota in ("receitas", "estoque", "eventos"):
        state = {"veredito_juiz": "corrija", "rota": rota}

        assert decidir_pos_juiz(state) == rota


@pytest.mark.parametrize("rota", ["faq", "fallback", "", "lixo"])
def test_juiz_nao_devolve_para_rota_sem_agente(rota):
    """Devolver para faq ou fallback nao tem aresta: derrubaria o grafo."""

    state = {"veredito_juiz": "corrija", "rota": rota}

    assert decidir_pos_juiz(state) == "orquestrador"


def test_juiz_aprovado_segue_para_o_orquestrador():
    assert decidir_pos_juiz({"veredito_juiz": "", "rota": "estoque"}) == "orquestrador"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("VEREDITO: APROVADO\nMOTIVO:", ("APROVADO", "")),
        ("VEREDITO: DEVOLVER\nMOTIVO: refaca a soma", ("DEVOLVER", "refaca a soma")),
        ("veredito: devolver\nmotivo: faltou lastro", ("DEVOLVER", "faltou lastro")),
        ("VEREDITO: DEVOLVER\nMOTIVO:", ("APROVADO", "")),
        ("sem formato nenhum", ("APROVADO", "")),
        ("", ("APROVADO", "")),
    ],
)
def test_veredito_falha_para_aprovado(texto, esperado):
    """Juiz fora de formato nao pode travar a resposta do usuario."""

    assert _ler_veredito(texto) == esperado


def test_teto_de_devolucoes_e_uma():
    assert LIMITE_DEVOLUCOES == 1


# ----------------------------------------------------------- evidências

def test_evidencia_vazia_e_anunciada():
    assert _formatar_evidencias([]) == "nenhuma"


def test_evidencia_longa_e_truncada_com_aviso():
    evidencias = [{"ferramenta": "get_stock", "conteudo": "y" * 400}] * 30

    bloco = _formatar_evidencias(evidencias)

    assert "omitidos por tamanho" in bloco
    assert len(bloco) < 30 * 400


def test_evidencia_sem_campos_nao_quebra():
    assert _formatar_evidencias([{}]) .startswith("- ferramenta:")


# ------------------------------------------------- confiança do juiz

def test_confianca_ausente_conta_como_certeza():
    _, _, confianca = _ler_veredito_completo("VEREDITO: DEVOLVER\nMOTIVO: x")

    assert confianca == 1.0


def test_confianca_aceita_decimal_virgula_e_porcentagem():
    for texto, esperado in (
        ("CONFIANCA: 0.4", 0.4),
        ("CONFIANCA: 0,55", 0.55),
        ("CONFIANCA: 85%", 0.85),
        ("CONFIANÇA: 30%", 0.3),
    ):
        _, _, confianca = _ler_veredito_completo(
            f"VEREDITO: DEVOLVER\n{texto}\nMOTIVO: x"
        )

        assert confianca == esperado, texto


def test_confianca_fica_na_faixa():
    for texto in ("CONFIANCA: -3", "CONFIANCA: 9999"):
        _, _, confianca = _ler_veredito_completo(
            f"VEREDITO: DEVOLVER\n{texto}\nMOTIVO: x"
        )

        assert 0.0 <= confianca <= 1.0, texto


def test_devolucao_sem_motivo_continua_aprovando():
    veredito, motivo, _ = _ler_veredito_completo("VEREDITO: DEVOLVER\nCONFIANCA: 0.2")

    assert veredito == "APROVADO"
    assert motivo == ""


def test_segunda_leitura_so_para_devolucao_insegura():
    def pede_segunda(texto):
        veredito, _, confianca = _ler_veredito_completo(texto)

        return veredito == "DEVOLVER" and confianca < CONFIANCA_PARA_DEVOLVER

    assert pede_segunda("VEREDITO: DEVOLVER\nCONFIANCA: 0.4\nMOTIVO: x")
    assert not pede_segunda("VEREDITO: DEVOLVER\nCONFIANCA: 0.9\nMOTIVO: x")
    assert not pede_segunda("VEREDITO: APROVADO\nCONFIANCA: 0.4\nMOTIVO:")


def test_segunda_opiniao_usa_semente_diferente():
    """Mesma semente e temperatura zero devolveriam o mesmo veredito."""

    from app.core.llms import juiz_llm, revisao_segunda_llm

    primeira = juiz_llm.model_kwargs.get("seed")
    segunda = revisao_segunda_llm.model_kwargs.get("seed")

    assert primeira is not None
    assert segunda is not None
    assert primeira != segunda


# ------------------------------------------------- percentil das métricas

def test_percentil_sem_dados_e_zero():
    assert _percentil([], 95) == 0.0


def test_percentil_pega_o_extremo_certo():
    valores = [float(n) for n in range(1, 101)]

    # Percentil por indice: p95 e o elemento 95 de 100, nao interpolacao.
    assert _percentil(valores, 0) == 1.0
    assert _percentil(valores, 50) == 51.0
    assert _percentil(valores, 95) == 95.0
    assert _percentil(valores, 100) == 100.0
