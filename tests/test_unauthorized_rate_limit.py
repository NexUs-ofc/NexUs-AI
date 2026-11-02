import unittest

from app.auth.unauthorized_rate_limit import UnauthorizedRateLimiter, ip_cliente


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class UnauthorizedRateLimiterTest(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.limiter = UnauthorizedRateLimiter(
            limite=10,
            janela_s=60,
            bloqueio_s=30,
            relogio=self.clock,
        )

    def test_blocks_after_ten_consecutive_unauthorized_responses(self):
        for _ in range(9):
            self.limiter.observar("192.0.2.10", 401)
        self.assertEqual(self.limiter.retry_after("192.0.2.10"), 0)

        self.limiter.observar("192.0.2.10", 401)
        self.assertEqual(self.limiter.retry_after("192.0.2.10"), 30)

    def test_non_401_resets_the_consecutive_count(self):
        for _ in range(9):
            self.limiter.observar("192.0.2.10", 401)
        self.limiter.observar("192.0.2.10", 200)
        for _ in range(9):
            self.limiter.observar("192.0.2.10", 401)
        self.assertEqual(self.limiter.retry_after("192.0.2.10"), 0)

    def test_window_and_block_expire(self):
        for _ in range(10):
            self.limiter.observar("192.0.2.10", 401)
        self.clock.now += 31
        self.assertEqual(self.limiter.retry_after("192.0.2.10"), 0)

        for _ in range(9):
            self.limiter.observar("192.0.2.10", 401)
        self.clock.now += 61
        self.assertEqual(self.limiter.retry_after("192.0.2.10"), 0)

    def test_uses_render_client_ip_and_ignores_forwarded_for(self):
        self.assertEqual(
            ip_cliente(
                {"cf-connecting-ip": "203.0.113.5", "x-forwarded-for": "198.51.100.7"},
                "127.0.0.1",
            ),
            "203.0.113.5",
        )
        self.assertEqual(
            ip_cliente({"x-forwarded-for": "198.51.100.7"}, "127.0.0.1"),
            "127.0.0.1",
        )


if __name__ == "__main__":
    unittest.main()
