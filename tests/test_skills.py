"""
As skills em Markdown e os agentes montados a partir delas.

O carregamento é por arquivo, então erro de digitação em frontmatter vira
agente mudo — e o loader avisa no log, que ninguém lê. Estes testes fazem o
aviso virar falha.
"""

import unittest
from dataclasses import FrozenInstanceError
from typing import ClassVar
from unittest.mock import patch

from langchain_core.tools import tool

from app.auth import identidade
from app.core.agents import (
    AGENTES_DAS_SKILLS,
    CATALOGO_FERRAMENTAS,
    OPERACOES_DE_ESCRITA,
    TAVILY_HABILITADAS,
    _ferramentas_da_skill,
    adiar_operacao_tool,
)
from app.core.skills import SKILLS, Skill, catalogo, do_agente, escolher_skill
from app.schemas import flow
from app.schemas.flow import ROTAS, SKILL_PADRAO

AGENTES_DE_DOMINIO = ("estoque", "receitas", "eventos")


class TestCarregamento(unittest.TestCase):
    def test_carregou_alguma_coisa(self):
        self.assertTrue(SKILLS, "nenhuma skill carregada — a pasta mudou de lugar?")

    def test_toda_skill_tem_frontmatter_completo(self):
        for nome, skill in SKILLS.items():
            with self.subTest(skill=nome):
                self.assertTrue(skill.titulo, "sem 'name'")
                self.assertTrue(skill.descricao, "sem 'description'")
                self.assertTrue(skill.dominio, "sem 'dominio'")
                self.assertIsInstance(skill.ferramentas, tuple, "'ferramentas' deve ser lista")
                self.assertTrue(skill.corpo.strip(), "corpo vazio")

    def test_a_pasta_define_o_agente(self):
        for nome, skill in SKILLS.items():
            with self.subTest(skill=nome):
                self.assertIn(skill.agente, AGENTES_DE_DOMINIO)

    def test_todo_agente_de_dominio_tem_ao_menos_uma_skill(self):
        for agente in AGENTES_DE_DOMINIO:
            with self.subTest(agente=agente):
                self.assertTrue(do_agente(agente))

    def test_nomes_de_skill_nao_se_repetem(self):
        self.assertEqual(len(SKILLS), len({s.nome for s in SKILLS.values()}))


class TestFerramentasDeclaradas(unittest.TestCase):
    """
    Regressao: tres skills de evento declaravam `recomendar_receita` e a
    ferramenta real se chama `recomend_recipe`. O loader avisava e seguia sem
    ela, deixando `evento-receitas` sem a ferramenta que da nome a skill.
    """

    def test_nenhuma_skill_declara_ferramenta_inexistente(self):
        for nome, skill in SKILLS.items():
            faltando = [f for f in skill.ferramentas
                        if f not in CATALOGO_FERRAMENTAS and f not in TAVILY_HABILITADAS]

            with self.subTest(skill=nome):
                self.assertEqual(faltando, [], f"{nome} declara {faltando}")

    def test_nenhuma_ferramenta_fica_orfa(self):
        """Ferramenta sem skill e codigo que nunca roda."""

        usadas = {f for s in SKILLS.values() for f in s.ferramentas}
        orfas = sorted(set(CATALOGO_FERRAMENTAS) - usadas)

        self.assertEqual(orfas, [], f"ferramentas que nenhuma skill usa: {orfas}")

    def test_todas_as_operacoes_de_escrita_tem_ferramenta_registrada(self):
        ausentes = OPERACOES_DE_ESCRITA - set(CATALOGO_FERRAMENTAS)
        self.assertEqual(ausentes, set())

    def test_todo_agente_montado_recebe_as_ferramentas_da_skill(self):
        for nome in SKILLS:
            with self.subTest(skill=nome):
                self.assertIn(nome, AGENTES_DAS_SKILLS)

    def test_skills_com_escrita_so_recebem_a_ferramenta_de_adiamento(self):
        for nome, skill in SKILLS.items():
            ferramentas = {f.name for f in _ferramentas_da_skill(skill)}
            escritas = set(skill.ferramentas) & OPERACOES_DE_ESCRITA
            if escritas:
                with self.subTest(skill=nome):
                    self.assertTrue(escritas.isdisjoint(ferramentas))
                    self.assertIn("adiar_operacao", ferramentas)
                    self.assertTrue((set(skill.ferramentas) - OPERACOES_DE_ESCRITA).issubset(ferramentas))

    def test_enum_da_ferramenta_de_adiamento_restringe_a_allowlist(self):
        schema = adiar_operacao_tool.args_schema
        self.assertEqual(set(schema.model_fields), {"operacao", "argumentos", "justificativa"})
        schema_json = schema.model_json_schema()
        self.assertEqual(set(schema_json["properties"]["operacao"]["enum"]), OPERACOES_DE_ESCRITA)
        self.assertEqual(schema_json["properties"]["argumentos"]["type"], "object")
        with self.assertRaises(ValueError):
            schema.model_validate({
                "operacao": "drop_database", "argumentos": {}, "justificativa": "apagar",
            })

    def test_tool_de_adiamento_fica_limitada_as_escritas_da_skill(self):
        skill = SKILLS["lista-montar"]
        defer_tool = next(tool for tool in _ferramentas_da_skill(skill)
                          if tool.name == "adiar_operacao")
        operation_schema = defer_tool.args_schema.model_json_schema()["properties"]["operacao"]
        allowed = set(operation_schema.get("enum", [operation_schema.get("const")]))
        self.assertEqual(allowed, {"create_list"})

    def test_argumentos_adiados_usam_o_schema_especifico_da_operacao(self):
        schema = adiar_operacao_tool.args_schema
        proposta_payload = {
            "operacao": "create_event",
            "argumentos": {
                "titulo": "Jantar", "descricao": "Jantar em família", "data": "2026-11-03",
                "inicio": "14:00", "fim": "16:00",
                "duracao": 120, "local": "Casa", "qtd_pessoas": 6,
            },
            "justificativa": "A pessoa pediu para criar este evento.",
        }
        proposta = schema.model_validate(proposta_payload)

        self.assertEqual(proposta.operacao, "create_event")
        with identidade.da_requisicao(124, 124):
            adiar_operacao_tool.invoke(proposta_payload)
            queued = identidade.obter_operacoes_pendentes()
        self.assertEqual(queued[0]["operacao"], "create_event")
        self.assertEqual(queued[0]["argumentos"].qtd_pessoas, 6)
        self.assertNotIsInstance(queued[0]["argumentos"], dict)

    def test_operacao_negada_nao_invoca_ferramenta_de_escrita(self):
        writes = []

        @tool("create_event")
        def fake_create_event(titulo: str, descricao: str, data: str,
                              duracao: int, local: str, qtd_pessoas: int) -> str:
            """Fake write tool."""
            writes.append(titulo)
            return "ok"

        with identidade.da_requisicao(124, 124):
            identidade.adiar_operacao("create_event", {
                "titulo": "Jantar", "descricao": "jantar", "data": "2026-11-03",
                "inicio": "14:00", "duracao": 120, "local": "casa", "qtd_pessoas": 6,
            }, "pedido")
            with (patch.dict(CATALOGO_FERRAMENTAS, {"create_event": fake_create_event}),
                  patch.object(flow, "_juiz_autoriza_gravacao", return_value=False)):
                flow._executar_operacoes_adiadas("Crie um jantar", "test-denied")
            self.assertEqual(writes, [])
            self.assertEqual(identidade.relatorio_operacoes()[0]["status"], "negada")

    def test_falha_da_ferramenta_no_banco_nao_vira_sucesso(self):
        writes = []

        @tool("create_event")
        def fake_create_event(titulo: str, descricao: str, data: str,
                              duracao: int, local: str, qtd_pessoas: int) -> str:
            """Simula uma falha explícita do banco após aprovação do juiz."""
            writes.append(titulo)
            return "FALHA: banco indisponível"

        with identidade.da_requisicao(124, 124):
            identidade.adiar_operacao("create_event", {
                "titulo": "Jantar", "descricao": "jantar", "data": "2026-11-03",
                "inicio": "14:00", "duracao": 120, "local": "casa", "qtd_pessoas": 6,
            }, "pedido")
            with (patch.dict(CATALOGO_FERRAMENTAS, {"create_event": fake_create_event}),
                  patch.object(flow, "_juiz_autoriza_gravacao", return_value=True)):
                evidences = flow._executar_operacoes_adiadas("Crie um jantar", "test-db-error")

            self.assertEqual(writes, ["Jantar"])
            self.assertEqual(identidade.relatorio_operacoes()[0]["status"], "falhou")
            self.assertTrue(identidade.gravacao_negada())
            self.assertIn("FALHA: banco indisponível", evidences[0]["conteudo"])

    def test_operacoes_dependentes_usam_id_real_da_operacao_aprovada(self):
        writes = []

        @tool("create_event")
        def fake_create_event(titulo: str, descricao: str, data: str,
                              duracao: int, local: str, qtd_pessoas: int) -> dict:
            """Fake event write tool."""
            writes.append(("evento", titulo))
            return {"_id": "event-123"}

        @tool("add_recipe")
        def fake_add_recipe(event_id: str, titulo: str = "") -> str:
            """Fake recipe write tool."""
            writes.append(("receita", event_id))
            return "ok"

        with identidade.da_requisicao(124, 124):
            identidade.adiar_operacao("create_event", {
                "titulo": "Jantar", "descricao": "jantar", "data": "2026-11-03",
                "inicio": "14:00", "duracao": 120, "local": "casa", "qtd_pessoas": 6,
            }, "pedido")
            identidade.adiar_operacao(
                "add_recipe", {"event_id": "$op-1._id", "titulo": "Prato"}, "vincular",
            )
            with (patch.dict(CATALOGO_FERRAMENTAS, {
                    "create_event": fake_create_event, "add_recipe": fake_add_recipe,
                  }), patch.object(flow, "_juiz_autoriza_gravacao", return_value=True)):
                flow._executar_operacoes_adiadas("Crie evento e vincule prato", "test-dependent")
            self.assertEqual(writes, [("evento", "Jantar"), ("receita", "event-123")])
            self.assertEqual([r["status"] for r in identidade.relatorio_operacoes()],
                             ["concluida", "concluida"])


class TestPromptMontado(unittest.TestCase):
    def setUp(self):
        self.skill = next(iter(SKILLS.values()))

    def test_prompt_tem_as_camadas_compartilhadas(self):
        from app.core.prompts.prompt_base import (
            ENTRADA_PADRAO,
            ENVELOPE_SAIDA,
            REGRAS_GERAIS,
            SYSTEM_PROMPT_AGENTE,
        )

        prompt = self.skill.prompt()

        for camada in (SYSTEM_PROMPT_AGENTE, REGRAS_GERAIS, ENTRADA_PADRAO, ENVELOPE_SAIDA):
            with self.subTest(camada=camada[:40]):
                self.assertIn(camada.strip()[:60], prompt)

    def test_o_corpo_da_skill_entra_no_prompt(self):
        self.assertIn(self.skill.corpo.strip()[:80], self.skill.prompt())

    def test_o_preambulo_entra_quando_passado(self):
        prompt = self.skill.prompt("PREAMBULO DE TESTE")

        self.assertIn("PREAMBULO DE TESTE", prompt)

    def test_sem_preambulo_nao_sobra_separador_solto(self):
        self.assertNotIn("\n\n\n\n\n\n", self.skill.prompt())

    def test_o_agente_nao_recebe_a_voz_do_orquestrador(self):
        """
        O agente devolve JSON; quem escreve para a pessoa e o orquestrador.
        Mandar as regras de prosa para o agente custava ~250 tokens por ida.
        """

        from app.core.prompts.prompt_base import VOZ

        self.assertNotIn(VOZ.strip()[:60], self.skill.prompt())

    def test_todo_prompt_tem_tamanho_plausivel(self):
        for nome, skill in SKILLS.items():
            with self.subTest(skill=nome):
                tokens = len(skill.prompt()) // 4

                self.assertGreater(tokens, 500, f"{nome} suspeito de estar truncado")
                self.assertLess(tokens, 4000, f"{nome} grande demais para o teto de TPM")


class TestCatalogo(unittest.TestCase):
    def test_catalogo_lista_as_skills_do_agente(self):
        texto = catalogo("estoque")

        for skill in do_agente("estoque"):
            with self.subTest(skill=skill.nome):
                self.assertIn(skill.nome, texto)

    def test_catalogo_nao_vaza_skill_de_outro_agente(self):
        texto = catalogo("estoque")

        for skill in do_agente("receitas"):
            with self.subTest(skill=skill.nome):
                self.assertNotIn(skill.nome, texto)

    def test_agente_inexistente_da_catalogo_vazio(self):
        self.assertEqual(catalogo("nao_existe"), "")


class TestSkillPadrao(unittest.TestCase):
    def test_o_padrao_aponta_para_skill_que_existe(self):
        for agente, skill in SKILL_PADRAO.items():
            with self.subTest(agente=agente):
                self.assertIn(skill, SKILLS)

    def test_o_padrao_cobre_todo_agente_de_dominio(self):
        self.assertEqual(set(SKILL_PADRAO), set(AGENTES_DE_DOMINIO))

    def test_escolha_deterministica_preserva_objetivo_da_skill(self):
        casos = [
            ("receitas", "Faça uma receita com o que tenho no estoque", None,
             "receita-do-estoque"),
            ("receitas", "Faça uma receita sem leite", None,
             "receita-com-restricao"),
            ("receitas", "Complete esta receita: falta a quantidade de sal", None,
             "receita-com-restricao"),
            ("receitas", "Esta receita está completa para ser salva?", None,
             "receita-com-restricao"),
            ("receitas", "Salve essa receita", "receita", "receita-anterior"),
            ("eventos", "A receita está associada ao evento?", "evento",
             "evento-receitas"),
            ("estoque", "Quais produtos vencem esta semana?", None,
             "estoque-validade"),
            ("eventos", "Monte uma lista de compras", None, "lista-montar"),
            ("eventos", "Monte uma lista de compras e prepare o evento, salve essa receita também", None,
             "evento-criar-completo"),
        ]
        for agente, pedido, contexto, esperado in casos:
            with self.subTest(agente=agente, pedido=pedido):
                nome, _ = escolher_skill(agente, pedido, contexto)
                self.assertEqual(nome, esperado)

    FERRAMENTAS_DE_ESCRITA: ClassVar[set[str]] = {
        "remove_product", "create_event", "cancel_event",
        "create_list", "update_list", "salvar_receita", "add_recipe",
        "remove_recipe", "postpone_event", "update_description",
    }

    def _escrita_do_padrao(self, agente: str) -> set:
        return set(SKILLS[SKILL_PADRAO[agente]].ferramentas) & self.FERRAMENTAS_DE_ESCRITA

    def test_o_padrao_de_estoque_e_receitas_so_le(self):
        """
        Quando o seletor nao decide, cai no padrao. Dar ferramenta de escrita
        a um palpite e pior do que responder de menos.
        """

        for agente in ("estoque", "receitas"):
            with self.subTest(agente=agente):
                self.assertEqual(self._escrita_do_padrao(agente), set())

    def test_estoque_nao_oferece_ferramentas_de_inclusao(self):
        ferramentas = set(CATALOGO_FERRAMENTAS)

        self.assertTrue(
            {"add_product", "resolver_alimento", "get_foods", "estimar_validade"}.isdisjoint(ferramentas)
        )
        self.assertNotIn("estoque-registrar", SKILLS)

    def test_skill_sem_estoque_nao_recebe_ferramentas(self):
        self.assertEqual(SKILLS["receita-sem-estoque"].ferramentas, ())

    @unittest.expectedFailure
    def test_o_padrao_de_eventos_deveria_so_ler(self):
        """
        LACUNA CONHECIDA, marcada para ficar visivel no relatorio.

        `evento-gerenciar` e o padrao de eventos e pode `cancel_event`,
        `postpone_event` e `update_description`. Ou seja: o seletor falhando
        deixa um palpite capaz de cancelar o evento da pessoa.

        Nao da para so trocar o padrao — nenhuma das cinco skills de eventos
        e de leitura pura. O conserto e criar uma `evento-consultar` com
        get_events e nada mais, e apontar SKILL_PADRAO para ela. Quando isso
        acontecer, este teste passa a dar "unexpected success" e deve ser
        promovido ao teste estrito acima.
        """

        self.assertEqual(self._escrita_do_padrao("eventos"), set())


class TestRotas(unittest.TestCase):
    def test_todo_agente_de_dominio_e_uma_rota(self):
        for agente in AGENTES_DE_DOMINIO:
            with self.subTest(agente=agente):
                self.assertIn(agente, ROTAS)

    def test_o_roteador_conhece_todas_as_rotas(self):
        from app.core.prompts.prompt_roteador import ROTEADOR_PROMPT_COMPLETO

        for rota in ROTAS:
            with self.subTest(rota=rota):
                self.assertIn(rota, ROTEADOR_PROMPT_COMPLETO)


class TestDataclass(unittest.TestCase):
    def test_skill_e_imutavel(self):
        """Congelada de proposito: skill alterada em runtime vira bug fantasma."""

        skill = next(iter(SKILLS.values()))

        with self.assertRaises(FrozenInstanceError):
            skill.nome = "outro"

    def test_ferramentas_e_tupla(self):
        for nome, skill in SKILLS.items():
            with self.subTest(skill=nome):
                self.assertIsInstance(skill.ferramentas, tuple)

    def test_e_mesmo_a_dataclass_esperada(self):
        self.assertIsInstance(next(iter(SKILLS.values())), Skill)


class TestBudgetFallback(unittest.TestCase):
    def test_resposta_de_limite_informa_operacoes_ja_concluidas(self):
        from contextlib import nullcontext

        from app.core.runtime_budget import BudgetExceeded

        def interromper(*args, **kwargs):
            identidade.registrar_resultado_operacao("salvar_receita", "concluida")
            raise BudgetExceeded("model_budget_exhausted")

        with (patch.object(flow.ConversationsRepository, "sessao_recente", return_value=None),
              patch.object(flow.ConversationsRepository, "create_session",
                           return_value="507f1f77bcf86cd799439011"),
              patch.object(flow.ConversationsRepository, "append_messages", return_value=True),
              patch.object(flow.ceris_workflow, "invoke", side_effect=interromper),
              patch.object(flow, "em_segundo_plano"),
              patch.object(flow, "trace", return_value=nullcontext()),
              patch.object(flow, "prever_respostas_recomendadas", return_value=[]),
              patch.object(flow.logger, "exception")):
            resposta = flow.executar_chat("Salve a receita e crie o evento", None, 124, 124)

        self.assertIn("Concluí: salvamento da receita.", resposta["resposta"])
        self.assertIn("limite de processamento", resposta["resposta"])



if __name__ == "__main__":
    unittest.main()

