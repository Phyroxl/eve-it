"""Tests for tax_service.py — character-specific fee calculation."""
import unittest
from unittest.mock import MagicMock, patch
from core.tax_service import TaxService, CharacterTaxes


CHAR_ID = 93000001
LOC_JITA = 60003760  # Jita 4-4, NPC station
FACTION_CALDARI = 500001
CORP_CALDARI_NAVY = 1000125

TOKEN = "test_token"


def _make_service(standings=None, standings_status="ready", br_lvl=5, acc_lvl=5):
    svc = TaxService.__new__(TaxService)
    svc.client = MagicMock()
    svc.location_cache = {}
    svc.overrides = {}
    svc._debug_printed = set()
    svc.char_taxes = {
        CHAR_ID: CharacterTaxes(
            sales_tax_pct=8.0 * (1.0 - 0.11 * acc_lvl),
            broker_fee_pct=3.0 - 0.3 * br_lvl,
            accounting_lvl=acc_lvl,
            broker_relations_lvl=br_lvl,
            status="ready",
            standings=standings or {},
            standings_status=standings_status,
            source="REAL ESI",
        )
    }
    return svc


class TestSalesTaxFormula(unittest.TestCase):

    def test_accounting_5_gives_360(self):
        """Accounting level 5 → 8% * 0.45 = 3.60%."""
        result = 8.0 * (1.0 - 0.11 * 5)
        self.assertAlmostEqual(result, 3.6, places=4)

    def test_accounting_0_gives_800(self):
        result = 8.0 * (1.0 - 0.11 * 0)
        self.assertAlmostEqual(result, 8.0, places=4)

    def test_override_sales_tax_337(self):
        """tax_overrides.json can set sales_tax_pct = 3.37 for structure traders."""
        svc = _make_service()
        svc.overrides = {str(CHAR_ID): {"sales_tax_pct": 3.37}}
        taxes = svc.get_taxes(CHAR_ID)
        self.assertAlmostEqual(taxes.sales_tax_pct, 3.37, places=4)
        self.assertEqual(taxes.source, "CALIBRADO MANUAL")


class TestBrokerFeeWithStandings(unittest.TestCase):

    def _loc_info_jita(self, svc):
        svc.location_cache[LOC_JITA] = {
            "type": "npc",
            "corp": CORP_CALDARI_NAVY,
            "faction": FACTION_CALDARI,
        }

    def test_no_standings_gives_base_fee(self):
        """BR5 with no standings → 1.50%."""
        svc = _make_service(standings={}, standings_status="ready")
        self._loc_info_jita(svc)
        fee, src = svc.get_effective_broker_fee(CHAR_ID, LOC_JITA, TOKEN)
        self.assertAlmostEqual(fee, 1.50, places=4)

    def test_caldari_standing_233_gives_143(self):
        """BR5 + Caldari State standing 2.33 → 1.50 - 0.0699 ≈ 1.43%."""
        standings = {FACTION_CALDARI: 2.33}
        svc = _make_service(standings=standings, standings_status="ready")
        self._loc_info_jita(svc)
        fee, src = svc.get_effective_broker_fee(CHAR_ID, LOC_JITA, TOKEN)
        self.assertAlmostEqual(fee, 1.5 - 0.03 * 2.33, places=4)
        self.assertIn("STANDINGS", src)

    def test_standings_idle_skips_reduction(self):
        """standings_status='idle' → no reduction applied → base fee only."""
        standings = {FACTION_CALDARI: 5.0}
        svc = _make_service(standings=standings, standings_status="idle")
        self._loc_info_jita(svc)
        fee, src = svc.get_effective_broker_fee(CHAR_ID, LOC_JITA, TOKEN)
        self.assertAlmostEqual(fee, 1.50, places=4)
        self.assertIn("pendientes", src)

    def test_combined_faction_and_corp_standings(self):
        """Faction standing 2.0 + Corp standing 1.5 → reduction = 0.06+0.03 = 0.09%."""
        standings = {FACTION_CALDARI: 2.0, CORP_CALDARI_NAVY: 1.5}
        svc = _make_service(standings=standings, standings_status="ready")
        self._loc_info_jita(svc)
        fee, src = svc.get_effective_broker_fee(CHAR_ID, LOC_JITA, TOKEN)
        expected = 1.50 - (0.03 * 2.0 + 0.02 * 1.5)
        self.assertAlmostEqual(fee, expected, places=4)

    def test_missing_scope_no_standings(self):
        """standings_status='missing_scope' → no standings reduction, appropriate source."""
        svc = _make_service(standings={}, standings_status="missing_scope")
        self._loc_info_jita(svc)
        fee, src = svc.get_effective_broker_fee(CHAR_ID, LOC_JITA, TOKEN)
        self.assertAlmostEqual(fee, 1.50, places=4)
        self.assertIn("sin Standings", src)

    def test_structure_location_gives_estimate(self):
        """Structure location → 1.0% (estimate)."""
        svc = _make_service()
        svc.location_cache[1_000_000_000_001] = {"type": "structure", "corp": None, "faction": None}
        fee, src = svc.get_effective_broker_fee(CHAR_ID, 1_000_000_000_001, TOKEN)
        self.assertAlmostEqual(fee, 1.0, places=4)
        self.assertIn("ESTRUCTURA", src)

    def test_override_broker_fee_143(self):
        """Manual override bypasses ESI computation."""
        svc = _make_service()
        svc.overrides = {str(CHAR_ID): {"broker_fee_pct": 1.43}}
        self._loc_info_jita(svc)
        fee, src = svc.get_effective_broker_fee(CHAR_ID, LOC_JITA, TOKEN)
        self.assertAlmostEqual(fee, 1.43, places=4)
        self.assertIn("CALIBRADO", src)

    def test_location_specific_override_takes_priority(self):
        """Location-specific override beats global override."""
        svc = _make_service()
        svc.overrides = {
            str(CHAR_ID): [
                {"location_id": LOC_JITA, "broker_fee_pct": 1.43},
                {"broker_fee_pct": 1.80},
            ]
        }
        self._loc_info_jita(svc)
        fee, _ = svc.get_effective_broker_fee(CHAR_ID, LOC_JITA, TOKEN)
        self.assertAlmostEqual(fee, 1.43, places=4)

    def test_get_location_info_logs_on_corp_info_failure(self):
        """When corporation_info fails, faction is None and warning is logged."""
        svc = TaxService.__new__(TaxService)
        svc.client = MagicMock()
        svc.location_cache = {}
        svc.client.universe_stations.return_value = {"owner": CORP_CALDARI_NAVY, "name": "Jita 4-4"}
        svc.client.corporation_info.return_value = None  # API failure
        with self.assertLogs("eve.tax_service", level="WARNING") as cm:
            info = svc._get_location_info(LOC_JITA, TOKEN)
        self.assertIsNone(info["faction"])
        self.assertTrue(any("corporation_info" in msg for msg in cm.output))


class TestRefreshResetsLocationCache(unittest.TestCase):

    def test_refresh_clears_location_cache(self):
        """refresh_from_esi clears location_cache to force fresh faction lookups."""
        svc = TaxService.__new__(TaxService)
        svc.client = MagicMock()
        svc.location_cache = {LOC_JITA: {"type": "npc", "corp": 1, "faction": 2}}
        svc.char_taxes = {}
        svc.overrides = {}
        svc._debug_printed = set()

        svc.client.character_skills.return_value = {"skills": []}
        svc.client.character_standings.return_value = []

        with patch("core.tax_service.load_tax_overrides", return_value={}):
            svc.refresh_from_esi(CHAR_ID, TOKEN)

        self.assertEqual(svc.location_cache, {})


if __name__ == "__main__":
    unittest.main()
