import unittest
from core.market_candidate_selector import build_economic_candidates, prefilter_candidates, select_final_candidates
from core.market_models import FilterConfig

class TestMarketCandidateSelector(unittest.TestCase):
    def setUp(self):
        self.config = FilterConfig()
        self.config.capital_max = 1000
        self.config.spread_max_pct = 50
        self.config.margin_min_pct = 5
        self.config.exclude_plex = True

    def test_build_candidates_unsorted(self):
        # Buy orders desordenadas, Sell orders desordenadas
        grouped = {
            10: {
                'buy': [{'price': 50}, {'price': 100}, {'price': 70}],
                'sell': [{'price': 200}, {'price': 150}, {'price': 180}]
            }
        }
        cands = build_economic_candidates(grouped, self.config)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].best_buy, 100)
        self.assertEqual(cands[0].best_sell, 150)
        self.assertEqual(cands[0].spread_pct, 50.0)

    def test_build_candidates(self):
        grouped = {
            1: {
                'buy': [{'price': 100}, {'price': 90}],
                'sell': [{'price': 120}, {'price': 130}]
            },
            2: { # Profit negativo
                'buy': [{'price': 100}],
                'sell': [{'price': 80}]
            }
        }
        cands = build_economic_candidates(grouped, self.config)
        self.assertEqual(len(cands), 2)
        
        # Cand 1: Buy 100, Sell 120.
        c1 = next(c for c in cands if c.type_id == 1)
        self.assertEqual(c1.best_buy, 100)
        self.assertEqual(c1.best_sell, 120)
        self.assertGreater(c1.margin_pct, 0)
        
        c2 = next(c for c in cands if c.type_id == 2)
        self.assertLess(c2.margin_pct, 0)

    def test_prefilter_candidates(self):
        from core.market_candidate_selector import CandidateStats
        # 1. Valid
        c1 = CandidateStats(1, 100, 120, 20.0, 10.0, 10.0, 1, 1, 100.0)
        # 2. Too expensive
        c2 = CandidateStats(2, 2000, 2500, 25.0, 400.0, 20.0, 1, 1, 200.0)
        # 3. High spread
        c3 = CandidateStats(3, 100, 1000, 900.0, 800.0, 800.0, 1, 1, 800.0)
        # 4. Low margin
        c4 = CandidateStats(4, 100, 104, 4.0, 0.1, 0.1, 1, 1, 1.0)
        # 5. PLEX
        c5 = CandidateStats(44992, 100, 120, 20.0, 10.0, 10.0, 1, 1, 100.0)
        
        cands = [c1, c2, c3, c4, c5]
        filtered, stats = prefilter_candidates(cands, self.config)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].type_id, 1)
        self.assertEqual(stats["capital"], 1)
        self.assertEqual(stats["spread"], 1)
        self.assertEqual(stats["margin"], 1)
        self.assertEqual(stats["plex"], 1)

    def test_select_final(self):
        from core.market_candidate_selector import CandidateStats
        c1 = CandidateStats(1, 10, 20, 100, 5, 50, 1, 1, 10.0)
        c2 = CandidateStats(2, 10, 20, 100, 5, 50, 1, 1, 50.0)
        c3 = CandidateStats(3, 10, 20, 100, 5, 50, 1, 1, 30.0)
        
        final = select_final_candidates([c1, c2, c3], limit=2)
        self.assertEqual(len(final), 2)
        self.assertEqual(final[0], 2) # Score 50
        self.assertEqual(final[1], 3) # Score 30

if __name__ == '__main__':
    unittest.main()
