"""
As skills em Markdown e os agentes montados a partir delas.

O carregamento é por arquivo, então erro de digitação em frontmatter vira
agente mudo — e o loader avisa no log, que ninguém lê. Estes testes fazem o
aviso virar falha.
"""

import unittest
from dataclasses import FrozenInstanceError
from typing import ClassVar

from app.core.agents import AGENTES_DAS_SKILLS, CATALOGO_FERRAMENTAS
from app.core.skills import SKILLS, Skill, catalogo, do_agente
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
                self.assertTrue(skill.ferramentas, "sem 'ferramentas'")
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
            faltando = [f for f in skill.ferramentas if f not in CATALOGO_FERRAMENTAS]

            with self.subTest(skill=nome):
                self.assertEqual(faltando, [], f"{nome} declara {faltando}")

    def test_nenhuma_ferramenta_fica_orfa(self):
        """Ferramenta sem skill e codigo que nunca roda."""

        usadas = {f for s in SKILLS.values() for f in s.ferramentas}
        orfas = sorted(set(CATALOGO_FERRAMENTAS) - usadas)

        self.assertEqual(orfas, [], f"ferramentas que nenhuma skill usa: {orfas}")

    def test_todo_agente_montado_recebe_as_ferramentas_da_skill(self):
        for nome in SKILLS:
            with self.subTest(skill=nome):
                self.assertIn(nome, AGENTES_DAS_SKILLS)


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

    FERRAMENTAS_DE_ESCRITA: ClassVar[set[str]] = {
        "add_product", "remove_product", "create_event", "cancel_event",
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


if __name__ == "__main__":
    unittest.main()
