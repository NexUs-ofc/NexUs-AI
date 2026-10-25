"""Regressões da retirada de inclusão de estoque do chat, sem rede."""

import ast
import json
import unittest
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


class SemInclusaoEstoqueTest(unittest.TestCase):
    def test_nao_existem_rotinas_de_inclusao_no_estoque(self):
        proibidas = {"add_product", "resolver_alimento", "create_food"}
        for pasta in ("app/tools", "app/repository/pgsql"):
            for arquivo in (ROOT / pasta).glob("*.py"):
                tree = ast.parse(arquivo.read_text(encoding="utf-8"))
                funcoes = {
                    n.name for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                self.assertFalse(funcoes & proibidas, arquivo.name)
        self.assertFalse((ROOT / "skills/estoque/estoque-registrar").joinpath("SKILL.md").exists())
        self.assertFalse((ROOT / "app/tools/validade_tools.py").exists())

    def test_faq_orienta_inclusao_pelas_telas_e_nega_inclusao_pelo_chat(self):
        faqs = json.loads((ROOT / "scripts/bases/NexUs_FAQs.json").read_text(encoding="utf-8"))
        resposta = next(f["resposta"] for f in faqs if f["pergunta"] == "Como adiciono um produto ao estoque?")
        self.assertIn("não adiciona produtos ao estoque", resposta)
        self.assertIn("tela de estoque", resposta)
        self.assertIn(resposta, (ROOT / "scripts/bases/NexUs_FAQs.md").read_text(encoding="utf-8"))

    def test_pdf_nao_autoriza_cadastro_pelo_assistente(self):
        texto = "\n".join(p.extract_text() or "" for p in PdfReader(ROOT / "scripts/bases/NexUs_doc.pdf").pages)
        self.assertNotIn("• cadastrar produtos;", texto)
        self.assertIn("não cadastrar nem adicionar produtos ao estoque pelo chat", texto)

    def test_outros_agentes_nao_oferecem_lancar_compras_no_estoque(self):
        for arquivo in (
            "app/core/prompts/prompt_events.py",
            "skills/eventos/lista-gerenciar/SKILL.md",
            "skills/estoque/estoque-consultar/SKILL.md",
        ):
            texto = (ROOT / arquivo).read_text(encoding="utf-8")
            self.assertNotIn("Quer que eu lance", texto)
            self.assertNotIn("deixe o agente de estoque registrar", texto)
            self.assertNotIn("Quer registrar o que você tem", texto)
