"""
Os endpoints que o painel do admin consome.

Depois que o front-end de health saiu, estes são contrato: só JSON, sempre
atrás da chave do painel menos o liveness, e nunca derrubando por dependência
fora.
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.app import app
from app.auth import admin_key_validator
from app.auth.admin_key_validator import validate_admin_key


class BaseAdmin(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[validate_admin_key] = lambda: "chave-de-teste"
        self.client = TestClient(app)

        self.addCleanup(app.dependency_overrides.clear)


class TestLiveness(BaseAdmin):
    def test_responde_sem_autenticacao(self):
        app.dependency_overrides.clear()

        r = TestClient(app).get("/health/")

        self.assertEqual(r.status_code, 200)

    def test_e_json_com_estado_e_uptime(self):
        corpo = self.client.get("/health/").json()

        self.assertEqual(corpo["estado"], "vivo")
        self.assertIn("uptime_segundos", corpo)
        self.assertIn("verificado_em", corpo)

    def test_rotas_antigas_de_health_sairam(self):
        """Métricas, relatório e dependências mudaram para /admin."""

        for rota in ("/health/metrics", "/health/report", "/health/dependencies"):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 404)


class TestChaveDoPainel(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_sem_chave_e_401(self):
        with patch.object(admin_key_validator, "ADMIN_API_KEY", "chave-certa"):
            self.assertEqual(self.client.get("/admin/session").status_code, 401)

    def test_chave_errada_e_401(self):
        with patch.object(admin_key_validator, "ADMIN_API_KEY", "chave-certa"):
            r = self.client.get("/admin/session", headers={"X-Admin-Key": "outra"})

        self.assertEqual(r.status_code, 401)

    def test_chave_certa_abre_a_sessao(self):
        with patch.object(admin_key_validator, "ADMIN_API_KEY", "chave-certa"):
            r = self.client.get("/admin/session", headers={"X-Admin-Key": "chave-certa"})

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["servico"], "ceris-ia")
        self.assertTrue(r.json()["autenticado"])

    def test_sem_chave_configurada_e_503(self):
        with patch.object(admin_key_validator, "ADMIN_API_KEY", None):
            r = self.client.get("/admin/session", headers={"X-Admin-Key": "qualquer"})

        self.assertEqual(r.status_code, 503)

    def test_api_key_do_aplicativo_nao_abre_o_painel(self):
        with patch.object(admin_key_validator, "ADMIN_API_KEY", "chave-certa"):
            r = self.client.get("/admin/metrics", headers={"X-API-Key": "chave-certa"})

        self.assertEqual(r.status_code, 401)


class TestMetricas(BaseAdmin):
    def test_devolve_as_secoes_da_pagina(self):
        with patch("app.controller.admin.montar_painel", return_value={"resumo": {}}) as montar:
            r = self.client.get("/admin/metrics?dias=14")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/json")
        montar.assert_called_once_with(14)

    def test_janela_fora_da_faixa_e_recusada(self):
        for dias in (0, -5, 1000):
            with self.subTest(dias=dias):
                self.assertEqual(self.client.get(f"/admin/metrics?dias={dias}").status_code, 422)

    def test_mongo_fora_nao_vira_500(self):
        """Painel sem dado é aceitável; painel com 500 não."""

        with patch("app.schemas.painel.MetricsRepository.listar", return_value=[]), \
             patch("app.schemas.painel.TracesRepository.listar", return_value=[]), \
             patch("app.schemas.painel.ToolMetricsRepository.listar", return_value=[]):
            r = self.client.get("/admin/metrics")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["resumo"]["execucoes"], 0)


class TestRelatorio(BaseAdmin):
    def test_devolve_o_relatorio_do_periodo(self):
        with patch("app.controller.admin.montar_relatorio", return_value={"indicadores": []}) as montar:
            r = self.client.get("/admin/report?dias=30")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"indicadores": []})
        montar.assert_called_once_with(30)


class TestLangSmith(BaseAdmin):
    def test_devolve_json_e_nao_html(self):
        """O HTML saiu: a apresentação é do painel."""

        with patch("app.controller.admin.gerar_relatorio", return_value={"projeto": "x"}):
            r = self.client.get("/admin/langsmith")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/json")
        self.assertEqual(r.json(), {"projeto": "x"})

    def test_parametros_chegam_ao_gerador(self):
        with patch("app.controller.admin.gerar_relatorio", return_value={}) as gerar:
            self.client.get("/admin/langsmith?dias=30&mensagens_semana=4&economia_mensal_brl=12.5")

        gerar.assert_called_once_with(
            dias=30, mensagens_semana=4, economia_mensal_brl=12.5, projeto=None,
        )


class TestDependencias(BaseAdmin):
    def test_devolve_o_estado_das_dependencias(self):
        with patch("app.controller.admin.checar_saude", return_value={"estado": "saudavel"}):
            r = self.client.get("/admin/dependencies")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"estado": "saudavel"})


class TestFrontEndRemovido(unittest.TestCase):
    """Não basta remover a rota: o mount de estáticos também servia HTML."""

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
