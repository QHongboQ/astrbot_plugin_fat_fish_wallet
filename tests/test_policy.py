"""Contracts for the public, shared Fat Fish wallet policy."""
from __future__ import annotations

import inspect
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "fatfish_policy_test_package"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_ROOT)]
sys.modules[PACKAGE_NAME] = package

from fatfish_policy_test_package.main import FatFishWalletGuard


class Provider:
    def __init__(self, model):
        self._model = model

    def meta(self):
        return types.SimpleNamespace(id=self._model, model=self._model, type="")


class Context:
    def get_provider_by_id(self, provider_id):
        return Provider(provider_id) if provider_id else None


class FatFishPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "enabled": True,
            "timezone": "Asia/Shanghai",
            "peak_periods": "14:00-18:00",
            "peak_weekdays": "0,1,2,3,4,5,6",
            "affected_providers": "deepseek",
            "gate_when_provider_unknown": True,
            "manual_override": "auto",
        }
        self.guard = FatFishWalletGuard(Context(), self.config)

    def policy(self, at, provider="deepseek/model"):
        return self.guard.get_wallet_policy(at=at, provider_id=provider)

    def test_october_7_2026_holiday_is_offpeak_in_auto_mode(self):
        at = datetime(2026, 10, 7, 14, 55, tzinfo=ZoneInfo("Asia/Shanghai"))
        policy = self.policy(at)
        self.assertTrue(policy["holiday"])
        self.assertTrue(policy["holiday_name"])
        self.assertTrue(policy["allowed"])
        self.assertEqual(policy["state"], "offpeak")
        self.guard._is_whitelisted = lambda _event: False
        event = types.SimpleNamespace(is_admin=lambda: False)
        self.assertEqual(self.guard._gate_decision(event, policy), (False, ""))
        self.config["manual_override"] = "always_block"
        blocked_policy = self.policy(at)
        self.assertFalse(blocked_policy["allowed"])
        self.assertEqual(self.guard._gate_decision(event, blocked_policy), (True, "manual"))

    def test_manual_block_wins_on_holiday_and_unaffected_provider(self):
        at = datetime(2026, 10, 7, 14, 55, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.config["manual_override"] = "always_block"
        self.config["affected_providers"] = "openai"
        policy = self.policy(at)
        self.assertTrue(policy["holiday"])
        self.assertFalse(policy["provider_affected"])
        self.assertFalse(policy["allowed"])
        self.assertEqual(policy["state"], "forced block")

    def test_manual_allow_wins_for_unaffected_provider(self):
        self.config["manual_override"] = "always_allow"
        self.config["affected_providers"] = "openai"
        policy = self.policy(datetime(2026, 10, 7, 14, 55))
        self.assertFalse(policy["provider_affected"])
        self.assertTrue(policy["allowed"])
        self.assertEqual(policy["state"], "forced allow")

    def test_disabled_wallet_allows_even_with_manual_block(self):
        self.config.update(enabled=False, manual_override="always_block")
        policy = self.policy(datetime(2026, 1, 5, 15, 0))
        self.assertFalse(policy["enabled"])
        self.assertTrue(policy["allowed"])

    def test_automatic_weekday_peak_blocks_affected_provider(self):
        at = datetime(2026, 1, 5, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        policy = self.policy(at)
        self.assertFalse(policy["holiday"])
        self.assertTrue(policy["provider_affected"])
        self.assertFalse(policy["allowed"])
        self.assertEqual(policy["state"], "peak")

    def test_missing_holiday_dependency_falls_back_to_time_policy(self):
        at = datetime(2026, 1, 5, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch.dict("sys.modules", {"holidays": None}):
            policy = self.policy(at)
        self.assertFalse(policy["holiday"])
        self.assertFalse(policy["allowed"])
        self.assertEqual(policy["state"], "peak")

    def test_message_gate_and_status_call_shared_public_policy(self):
        source = inspect.getsource(FatFishWalletGuard.peak_gate)
        status_source = inspect.getsource(FatFishWalletGuard.peak_status)
        self.assertIn("get_wallet_policy", source)
        self.assertIn("get_wallet_policy", status_source)

        event = types.SimpleNamespace(is_admin=lambda: False)
        self.guard._is_whitelisted = lambda _event: False
        self.config.update(manual_override="always_block", affected_providers="openai")
        policy = self.guard.get_wallet_policy(
            at=datetime(2026, 10, 7, 14, 55, tzinfo=ZoneInfo("Asia/Shanghai")),
            provider_id="deepseek/model",
        )
        self.assertEqual(self.guard._gate_decision(event, policy), (True, "manual"))


if __name__ == "__main__":
    unittest.main()
