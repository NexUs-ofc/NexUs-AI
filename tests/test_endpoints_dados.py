"""
Os endpoints que o painel do admin consome.

Depois que o front-end de health saiu, estes são contrato: só JSON, sempre
autenticados menos o liveness, e nunca derrubando por dependência fora.
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.app import app
from app.auth.tracing_key_validator import validate_api_key


class BaseHealth(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[validate_api_key] = lambda: "chave-de-teste"
        self.client = TestClient(app)

        self.addCleanup(app.dependency_overrides.clear)


class TestLiveness(BaseHealth):
    def test_responde_sem_autenticacao(self):
        app.dependency_overrides.clear()

        r = TestClient(app).get("/health/")

        self.assertEqual(r.status_code, 200)

    def test_e_json_com_estado_e_uptime(self):
        corpo = self.client.get("/health/").json()

        self.assertEqual(corpo["estado"], "vivo")
        self.assertIn("uptime_segundos", corpo)
        self.assertIn("verificado_em", corpo)


class TestMetricas(BaseHealth):
    def test_exige_chave(self):
        app.dependency_overrides.clear()

        self.assertEqual(TestClient(app).get("/health/metrics").status_code, 401)

    def test_devolve_as_duas_agregacoes(self):
        with patch("app.controller.health.MetricsRepository.resumo", return_value={"requisicoes": 0}), \
             patch("app.controller.health.TracesRepository.latencia_por_no", return_value=[]):
            r = self.client.get("/health/metrics")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/json")
        self.assertEqual(set(r.json()), {"requisicoes", "latencia_por_no"})

    def test_a_janela_e_repassada(self):
        with patch("app.controller.health.MetricsRepository.resumo", return_value={}) as resumo, \
             patch("app.controller.health.TracesRepository.latencia_por_no", return_value=[]) as nos:
            self.client.get("/health/metrics?horas=72")

        resumo.assert_called_once_with(72)
        nos.assert_called_once_with(72)

    def test_janela_fora_da_faixa_e_recusada(self):
        for horas in (0, -5, 10000):
            with self.subTest(horas=horas):
                self.assertEqual(self.client.get(f"/health/metrics?horas={horas}").status_code, 422)

    def test_mongo_fora_nao_vira_500(self):
        """Painel sem dado e aceitavel; painel com 500 nao."""

        with patch("app.controller.health.MetricsRepository.resumo", return_value={}), \
             patch("app.controller.health.TracesRepository.latencia_por_no", return_value=[]):
            r = self.client.get("/health/metrics")

        self.assertEqual(r.status_code, 200)


class TestRelatorio(BaseHealth):
    def test_exige_chave(self):
        app.dependency_overrides.clear()

        self.assertEqual(TestClient(app).get("/health/report").status_code, 401)

    def test_devolve_json_e_nao_html(self):
        """O HTML saiu: a apresentacao e do painel."""

        with patch("app.controller.health.gerar_relatorio", return_value={"projeto": "x"}):
            r = self.client.get("/health/report")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/json")
        self.assertEqual(r.json(), {"projeto": "x"})

    def test_parametros_chegam_ao_gerador(self):
        with patch("app.controller.health.gerar_relatorio", return_value={}) as gerar:
            self.client.get("/health/report?dias=30&mensagens_semana=4&economia_mensal_brl=12.5")

        gerar.assert_called_once_with(
            dias=30, mensagens_semana=4, economia_mensal_brl=12.5, projeto=None,
        )


class TestFrontEndRemovido(unittest.TestCase):
    """Nao basta remover a rota: o mount de estaticos tambem servia HTML."""

    def setUp(self):
        self.client = TestClient(app)

    def test_pagina_de_health_nao_existe_mais(self):
        self.assertEqual(self.client.get("/health/page").status_code, 404)

    def test_estaticos_nao_sao_mais_servidos(self):
        self.assertEqual(self.client.get("/static/health/page.html").status_code, 404)

    def test_nao_sobrou_rota_devolvendo_html(self):
        from fastapi.responses import HTMLResponse
        from fastapi.routing import APIRoute

        for rota in app.routes:
            if isinstance(rota, APIRoute):
                with self.subTest(rota=rota.path):
                    self.assertIsNot(rota.response_class, HTMLResponse)


if __name__ == "__main__":
    unittest.main()
