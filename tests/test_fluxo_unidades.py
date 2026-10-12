"""
As funções puras do grafo: as que decidem sem chamar modelo nenhum.

São baratas de testar e caras quando quebram, porque erram em silêncio — o
corte de evidência que reprovava resposta correta viveu meio dia aqui.
"""

import json
import unittest
from unittest.mock import patch

from app.schemas import flow


class TestSaudacao(unittest.TestCase):
    def test_reconhece_cumprimento(self):
        for msg in ("Oi", "oi!", "Olá", "ola tudo bem", "bom dia", "Boa tarde",
                    "boa noite", "opa", "e aí", "fala!", "hey", "hi", "hello",
                    "tudo bem?", "como vai"):
            with self.subTest(msg=msg):
                self.assertTrue(flow._saudou(msg))

    def test_nao_confunde_pedido_com_saudacao(self):
        for msg in ("o que está vencendo?", "me dá uma receita",
                    "e como eu marco como comprado?", "adiciona arroz",
                    "obrigado", "quero oi de pêssego"):
            with self.subTest(msg=msg):
                self.assertFalse(flow._saudou(msg))

    def test_saudacao_com_pedido_junto_ainda_conta_como_saudacao(self):
        """O orquestrador usa isto so para decidir se retribui o cumprimento."""

        self.assertTrue(flow._saudou("Oi, o que tenho no estoque?"))

    def test_entrada_vazia_nao_quebra(self):
        self.assertFalse(flow._saudou(""))
        self.assertFalse(flow._saudou(None))


class TestAgradecimento(unittest.TestCase):
    def test_reconhece_agradecimento_e_despedida(self):
        for msg in ("obrigado", "Obrigada!", "obg", "valeu", "vlw", "tchau",
                    "até mais", "falou"):
            with self.subTest(msg=msg):
                self.assertTrue(flow._AGRADECIMENTO.search(msg))

    def test_cumprimento_nao_e_agradecimento(self):
        for msg in ("oi", "bom dia", "boa noite", "tudo bem?"):
            with self.subTest(msg=msg):
                self.assertFalse(flow._AGRADECIMENTO.search(msg))


class TestNormalizarRota(unittest.TestCase):
    def test_rota_limpa_passa(self):
        for rota in flow.ROTAS:
            with self.subTest(rota=rota):
                self.assertEqual(flow._normalizar_rota(rota), rota)

    def test_sujeira_em_volta_e_tolerada(self):
        for bruto, esperado in (("Rota: estoque", "estoque"), ("estoque.", "estoque"),
                                ("  ESTOQUE  ", "estoque"), ("a rota e receitas", "receitas")):
            with self.subTest(bruto=bruto):
                self.assertEqual(flow._normalizar_rota(bruto), esperado)

    def test_desconhecido_cai_em_fallback(self):
        """Valor cru ia para o add_conditional_edges e derrubava o grafo."""

        for bruto in ("", "   ", "sei la", None, "123"):
            with self.subTest(bruto=bruto):
                self.assertEqual(flow._normalizar_rota(bruto), "fallback")


class TestUltimosTurnos(unittest.TestCase):
    def setUp(self):
        self.historico = [{"role": "user", "content": f"m{i}"} for i in range(20)]

    def test_corta_pelo_fim(self):
        turnos = flow._ultimos_turnos(self.historico, 4)

        self.assertEqual(len(turnos), 4)
        self.assertEqual(turnos[-1]["content"], "m19")

    def test_historico_menor_que_o_teto_volta_inteiro(self):
        curto = self.historico[:2]

        self.assertEqual(flow._ultimos_turnos(curto, 10), curto)

    def test_vazio_nao_quebra(self):
        self.assertEqual(flow._ultimos_turnos([], 5), [])


class TestCompactarEvidencia(unittest.TestCase):
    def _estoque(self, n):
        return json.dumps([
            {"pantry_item_id": i, "food_id": i, "food_name": f"Item {i}",
             "quantity": 1, "expiry_date": "2026-12-01"}
            for i in range(n)
        ], ensure_ascii=False)

    def test_ids_saem_e_nomes_ficam(self):
        texto, aviso = flow._compactar(self._estoque(3))

        self.assertNotIn("pantry_item_id", texto)
        self.assertNotIn("food_id", texto)
        self.assertIn("Item 0", texto)
        self.assertEqual(aviso, "")

    def test_compactar_encolhe_o_payload(self):
        bruto = self._estoque(11)
        texto, _ = flow._compactar(bruto)

        self.assertLess(len(texto), len(bruto))

    def test_corte_avisa_quantos_ficaram_de_fora(self):
        """Corte silencioso faz o juiz ler ausencia como inexistencia."""

        _, aviso = flow._compactar(self._estoque(200))

        self.assertIn("omitidos", aviso)

    def test_corte_nao_parte_item_no_meio(self):
        texto, _ = flow._compactar(self._estoque(200))

        self.assertFalse(texto.rstrip().endswith("="))
        self.assertNotIn("food_name=Item 1 quantity=1 expiry_date=2026-1\n", texto)

    def test_conteudo_nao_json_passa_inteiro(self):
        texto, aviso = flow._compactar("Nenhuma preferência registrada.")

        self.assertEqual(texto, "Nenhuma preferência registrada.")
        self.assertEqual(aviso, "")

    def test_texto_longo_nao_json_avisa_o_corte(self):
        _, aviso = flow._compactar("x" * 5000)

        self.assertIn("cortado", aviso)

    def test_json_quebrado_nao_derruba(self):
        texto, _ = flow._compactar('[{"a":')

        self.assertEqual(texto, '[{"a":')

    def test_lista_de_strings_passa_como_veio(self):
        texto, _ = flow._compactar('["a","b"]')

        self.assertEqual(texto, '["a","b"]')


class TestFormatarEvidencias(unittest.TestCase):
    def test_sem_evidencia_diz_nenhuma(self):
        self.assertEqual(flow._formatar_evidencias([]), "nenhuma")

    def test_o_nome_da_ferramenta_aparece(self):
        bloco = flow._formatar_evidencias([
            {"ferramenta": "get_stock", "conteudo": "[]"},
        ])

        self.assertIn("get_stock", bloco)

    def test_estoque_de_onze_itens_cabe_inteiro(self):
        """
        Regressao: o teto de 400 chars mostrava 4 de 11 itens, e o juiz
        reprovava os 7 que nao via.
        """

        itens = json.dumps([
            {"pantry_item_id": i, "food_id": i, "food_name": nome,
             "quantity": 1, "expiry_date": "2026-12-01"}
            for i, nome in enumerate([
                "Picanha", "Sal Grosso", "Peito de Frango", "Cogumelo Paris",
                "Creme de Leite", "Abóbora", "Pimentão", "Arroz Arbóreo",
                "Caldo de Legumes", "Azeite", "Cebola",
            ])
        ], ensure_ascii=False)

        bloco = flow._formatar_evidencias([{"ferramenta": "get_stock", "conteudo": itens}])

        for nome in ("Picanha", "Creme de Leite", "Pimentão", "Cebola"):
            with self.subTest(nome=nome):
                self.assertIn(nome, bloco)

    def test_muitas_ferramentas_param_no_teto_total(self):
        evidencias = [{"ferramenta": "t", "conteudo": "y" * 900}] * 30
        bloco = flow._formatar_evidencias(evidencias)

        self.assertIn("omitidos", bloco)
        self.assertLess(len(bloco), flow.LIMITE_EVIDENCIAS_TOTAL + 2000)


class TestPodarEnvelopeDoJuiz(unittest.TestCase):
    """
    O juiz nao pode conferir medida de cozinha contra um estoque que conta
    unidades. Deixar o campo a vista fazia ele reprovar toda receita.
    """

    def setUp(self):
        self.envelope = json.dumps({
            "dominio": "receitas",
            "resposta": "Dá para fazer um risoto.",
            "recomendacao": "Use o arroz que vence antes.",
            "receita": {
                "titulo": "Risoto",
                "porcoes": 2,
                "tempo_estimado": "45 minutos",
                "dificuldade": "media",
                "ingredientes": [
                    {"ingrediente": "Arroz Arbóreo", "quantidade_total": "200g",
                     "tem_suficiente": True},
                ],
                "instrucoes": ["Refogue o arroz."],
                "ingredientes_faltantes": [],
            },
        }, ensure_ascii=False)

    def test_medidas_somem(self):
        podado = flow._para_o_juiz(self.envelope)

        for campo in ("quantidade_total", "tem_suficiente", "porcoes",
                      "tempo_estimado", "dificuldade", "200g"):
            with self.subTest(campo=campo):
                self.assertNotIn(campo, podado)

    def test_nomes_de_ingrediente_ficam(self):
        """E ali que mora a alucinacao que o juiz precisa pegar."""

        self.assertIn("Arroz Arbóreo", flow._para_o_juiz(self.envelope))

    def test_texto_para_a_pessoa_fica(self):
        podado = flow._para_o_juiz(self.envelope)

        self.assertIn("Dá para fazer um risoto.", podado)
        self.assertIn("Use o arroz que vence antes.", podado)

    def test_poda_encolhe(self):
        self.assertLess(len(flow._para_o_juiz(self.envelope)), len(self.envelope))

    def test_nao_json_passa_igual(self):
        self.assertEqual(flow._para_o_juiz("texto solto"), "texto solto")

    def test_json_que_nao_e_objeto_passa_igual(self):
        self.assertEqual(flow._para_o_juiz("[1,2,3]"), "[1,2,3]")


class TestMontarSemModelo(unittest.TestCase):
    def test_junta_resposta_e_recomendacao(self):
        env = json.dumps({"resposta": "Você tem 3 ovos.", "recomendacao": "Use logo."})

        self.assertEqual(flow._montar_sem_modelo(env), "Você tem 3 ovos. Use logo.")

    def test_recomendacao_vazia_nao_deixa_espaco_sobrando(self):
        env = json.dumps({"resposta": "Você tem 3 ovos.", "recomendacao": ""})

        self.assertEqual(flow._montar_sem_modelo(env), "Você tem 3 ovos.")

    def test_nao_repete_o_que_ja_foi_dito(self):
        env = json.dumps({"resposta": "Descarte os vencidos.",
                          "recomendacao": "Descarte os vencidos."})

        self.assertEqual(flow._montar_sem_modelo(env), "Descarte os vencidos.")

    def test_esclarecer_encerra_a_mensagem_sozinho(self):
        env = json.dumps({"resposta": "Achei dois.", "recomendacao": "x",
                          "esclarecer": "Integral ou desnatado?"})

        self.assertEqual(flow._montar_sem_modelo(env), "Integral ou desnatado?")

    def test_saudacao_entra_so_quando_pedida(self):
        env = json.dumps({"resposta": "Você tem 3 ovos."})

        self.assertFalse(flow._montar_sem_modelo(env, False).startswith("Oi!"))
        self.assertTrue(flow._montar_sem_modelo(env, True).startswith("Oi!"))

    def test_envelope_inaproveitavel_devolve_vazio(self):
        """String vazia e o sinal para o orquestrador assumir."""

        for env in ("", "texto solto", "{nao e json", json.dumps({"resposta": ""}),
                    json.dumps([1, 2])):
            with self.subTest(env=env[:20]):
                self.assertEqual(flow._montar_sem_modelo(env), "")


class TestLerVeredito(unittest.TestCase):
    def test_aprovado(self):
        self.assertEqual(flow._ler_veredito("VEREDITO: APROVADO\nMOTIVO:"), ("APROVADO", ""))

    def test_devolver_com_motivo(self):
        veredito, motivo = flow._ler_veredito("VEREDITO: DEVOLVER\nMOTIVO: total nao fecha")

        self.assertEqual(veredito, "DEVOLVER")
        self.assertEqual(motivo, "total nao fecha")

    def test_devolver_sem_motivo_vira_aprovado(self):
        """Devolver sem dizer o que corrigir e rodada perdida."""

        self.assertEqual(flow._ler_veredito("VEREDITO: DEVOLVER"), ("APROVADO", ""))

    def test_fora_de_formato_aprova(self):
        for texto in ("", "sei la", "{}"):
            with self.subTest(texto=texto):
                self.assertEqual(flow._ler_veredito(texto)[0], "APROVADO")


class TestPreferenciasPreCarregadas(unittest.TestCase):
    def test_sem_preferencia_e_resposta_completa(self):
        with patch.object(flow.PreferencesRepository, "buscar_preferencias", return_value=[]):
            self.assertEqual(flow._preferencias_prontas(1, "oi"), "nenhuma preferência registrada")

    def test_preferencias_viram_uma_linha(self):
        with patch.object(flow.PreferencesRepository, "buscar_preferencias",
                          return_value=["sem lactose", "porções pequenas"]):
            texto = flow._preferencias_prontas(1, "oi")

        self.assertIn("sem lactose", texto)
        self.assertIn("porções pequenas", texto)

    def test_qdrant_fora_devolve_vazio_e_nao_derruba(self):
        """Vazio faz o agente cair na ferramenta, como era antes."""

        with patch.object(flow.PreferencesRepository, "buscar_preferencias",
                          side_effect=RuntimeError("qdrant fora")):
            self.assertEqual(flow._preferencias_prontas(1, "oi"), "")


class TestLimites(unittest.TestCase):
    def test_uma_devolucao_no_maximo(self):
        """Cada devolucao re-executa o agente: 43s medidos em estoque."""

        self.assertEqual(flow.LIMITE_DEVOLUCOES, 1)

    def test_evidencia_cabe_num_estoque_real(self):
        self.assertGreaterEqual(flow.LIMITE_EVIDENCIA, 1000)

    def test_historico_do_juiz_e_menor_que_o_do_agente(self):
        self.assertLess(flow.TURNOS_PARA_O_JUIZ, flow.TURNOS_PARA_O_AGENTE)


if __name__ == "__main__":
    unittest.main()
