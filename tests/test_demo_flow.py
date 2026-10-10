import unittest

from app.config import settings
from app.services.analyzer import TokenAnalyzer
from app.services.scoring import bot_assessment
from app.services.types import WalletActivity


class DemoFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_finds_human_convergence_and_rejects_shared_cluster(self):
        result = await TokenAnalyzer(settings).run(
            "So11111111111111111111111111111111111111112", "demo"
        )
        self.assertEqual(result["summary"]["early_buyers_found"], 20)
        self.assertEqual(result["summary"]["likely_bots"], 3)
        signals = {signal["symbol"]: signal for signal in result["signals"]}
        self.assertTrue(signals["MANGO"]["paper_track_eligible"])
        self.assertEqual(signals["MANGO"]["independent_wallet_count"], 3)
        self.assertFalse(signals["BREAD"]["paper_track_eligible"])
        self.assertEqual(signals["BREAD"]["independent_wallet_count"], 2)

    def test_fast_burst_has_high_bot_score(self):
        events = [
            WalletActivity(wallet="wallet", timestamp=1_000 + index * 8, side="buy")
            for index in range(100)
        ]
        assessment = bot_assessment(events, 1_500)
        self.assertEqual(assessment["label"], "likely_bot")
        self.assertGreaterEqual(assessment["score"], 60)


if __name__ == "__main__":
    unittest.main()
