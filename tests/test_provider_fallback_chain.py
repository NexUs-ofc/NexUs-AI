import unittest

import httpx

from app.core import provider_policy
from app.core.provider_policy import TransientFallback


class ProviderFallbackChainTest(unittest.TestCase):
    def tearDown(self):
        with provider_policy._circuit_lock:
            provider_policy._circuit_open_until.clear()

    def test_tenta_openai_gemini_e_groq_em_ordem(self):
        class Provider:
            def __init__(self, result):
                self.result = result
                self.calls = 0

            def invoke(self, value, config=None, **kwargs):
                self.calls += 1
                if isinstance(self.result, Exception):
                    raise self.result
                return self.result

        class OpenAI(Provider):
            pass

        class Gemini(Provider):
            pass

        class Groq(Provider):
            pass

        openai = OpenAI(httpx.ReadTimeout("openai"))
        gemini = Gemini(httpx.ReadTimeout("gemini"))
        groq = Groq("ok")

        result = TransientFallback(openai, [gemini, groq]).invoke("pedido")

        self.assertEqual(result, "ok")
        self.assertEqual((openai.calls, gemini.calls, groq.calls), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
