"""
Leitura em faixas, com o OCR de verdade.

As faixas existem para caber na RAM do servidor (572 MB de pico na imagem
inteira, 462 MB em faixas, medido no container). Este teste garante que o
corte em faixas nao perde nem duplica linha, inclusive a que cai na emenda.
"""

import unittest
from difflib import SequenceMatcher
from unittest.mock import patch

import cv2
import numpy as np

from app.tools import ocr_tools

LINHAS = [f"{i:03d} PRODUTO NUMERO {i} UN X {i},99" for i in range(1, 13)]


def _imagem() -> np.ndarray:
    altura = 60 + 52 * len(LINHAS)
    img = np.full((altura, 1100), 255, dtype=np.uint8)
    for i, linha in enumerate(LINHAS):
        cv2.putText(img, linha, (30, 60 + 52 * i), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2, cv2.LINE_AA)
    return img


class TestFaixas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.imagem = _imagem()
        with patch.object(ocr_tools, "FAIXA_ALTURA", 0):
            cls.inteira = ocr_tools.read_receipt(cls.imagem)["lines"]

    def test_imagem_inteira_le_todas_as_linhas(self):
        # Sanidade do proprio teste: sem faixas o OCR le todas as linhas.
        self.assertEqual(len(self.inteira), len(LINHAS))

    def test_faixas_leem_as_mesmas_linhas_sem_duplicar(self):
        # Altura que forca emendas no meio do texto.
        with patch.object(ocr_tools, "FAIXA_ALTURA", 250), patch.object(ocr_tools, "FAIXA_SOBREPOSICAO", 110):
            em_faixas = ocr_tools.read_receipt(self.imagem)["lines"]

        # Mesmas linhas, na mesma ordem e sem repeticao. O texto pode variar um
        # caractere ("7,99" x "7.99"): o OCR le cada recorte com outro contexto.
        self.assertEqual(len(em_faixas), len(self.inteira))
        self.assertEqual(len(set(em_faixas)), len(em_faixas))
        for faixa, inteira in zip(em_faixas, self.inteira, strict=True):
            self.assertGreaterEqual(SequenceMatcher(None, faixa, inteira).ratio(), 0.9, (faixa, inteira))

    def test_limite_da_deteccao_volta_ao_original(self):
        resize = ocr_tools._get_engine().text_detector.preprocess_op[0]
        antes = resize.limit_side_len

        with patch.object(ocr_tools, "FAIXA_ALTURA", 250):
            ocr_tools.read_receipt(self.imagem)

        self.assertEqual(resize.limit_side_len, antes)


if __name__ == "__main__":
    unittest.main()
