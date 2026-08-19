"""Unit tests for Loan Equity Verification and Boolean Preservation.

Verifies:
1. Explicit false deposit responses (e.g., {"meets_minimum": false}, {"meets_minimum": 0},
   [{"meets_minimum": 0}], 'insufficient', 'no') are strictly parsed as False.
2. Explicit true deposit responses (e.g., {"meets_minimum": true}, {"meets_minimum": 1},
   [{"meets_minimum": 1}], 'sufficient', 'yes') are parsed as True.
3. Substring collisions (such as 'sufficient' inside 'insufficient' or 'meets' inside 'meets_minimum')
   are safely prevented by prioritizing structured JSON parsing and negative checks.
4. CheckEquityOutput preserves has_sufficient_equity=False and preserves the custom calculation
   threshold (5436.66) unchanged in equity_check.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import patch, MagicMock
from pydantic import BaseModel, Field

# Import parser from loan module
from loan.loan import parse_deposit_equity_response, verify_deposit_equity, CheckEquityOutput


class TestEquityVerification(unittest.TestCase):
    """Test suite ensuring explicit booleans are preserved in loan equity checks."""

    def test_explicit_false_json_structures(self):
        """Confirm that various false JSON structures remain False."""
        self.assertFalse(parse_deposit_equity_response({"meets_minimum": False}))
        self.assertFalse(parse_deposit_equity_response({"meets_minimum": 0}))
        self.assertFalse(parse_deposit_equity_response([{"meets_minimum": 0}]))
        self.assertFalse(parse_deposit_equity_response([{"meets_minimum": False}]))
        self.assertFalse(parse_deposit_equity_response({"has_sufficient_equity": False}))
        self.assertFalse(parse_deposit_equity_response('{"meets_minimum": false}'))
        self.assertFalse(parse_deposit_equity_response('{"meets_minimum": 0}'))
        self.assertFalse(parse_deposit_equity_response('[{"meets_minimum": 0}]'))
        self.assertFalse(parse_deposit_equity_response('{"has_sufficient_equity": false}'))

    def test_explicit_true_json_structures(self):
        """Confirm that various true JSON structures parse as True."""
        self.assertTrue(parse_deposit_equity_response({"meets_minimum": True}))
        self.assertTrue(parse_deposit_equity_response({"meets_minimum": 1}))
        self.assertTrue(parse_deposit_equity_response([{"meets_minimum": 1}]))
        self.assertTrue(parse_deposit_equity_response([{"meets_minimum": True}]))
        self.assertTrue(parse_deposit_equity_response({"has_sufficient_equity": True}))
        self.assertTrue(parse_deposit_equity_response('{"meets_minimum": true}'))
        self.assertTrue(parse_deposit_equity_response('{"meets_minimum": 1}'))
        self.assertTrue(parse_deposit_equity_response('[{"meets_minimum": 1}]'))
        self.assertTrue(parse_deposit_equity_response('{"has_sufficient_equity": true}'))

    def test_negative_substring_protection(self):
        """Confirm 'sufficient' does NOT match 'insufficient' and 'meets' does NOT match 'meets_minimum: false'."""
        # 'insufficient' contains 'sufficient' as a substring, but must evaluate to False
        self.assertFalse(parse_deposit_equity_response("insufficient equity"))
        self.assertFalse(parse_deposit_equity_response("Customer has insufficient equity on deposit"))
        self.assertFalse(parse_deposit_equity_response("Deposit balance is insufficient for loan"))

        # String containing 'meets_minimum: false' contains substring 'meets', but must evaluate to False
        self.assertFalse(parse_deposit_equity_response('Result from deposit check: {"meets_minimum": false}'))
        self.assertFalse(parse_deposit_equity_response("Customer does not meet the minimum balance threshold."))
        self.assertFalse(parse_deposit_equity_response("No, total deposits do not exceed the minimum balance."))

    def test_positive_text_responses(self):
        """Confirm positive statements parse accurately as True."""
        self.assertTrue(parse_deposit_equity_response("Yes, customer total deposits exceed minimum balance."))
        self.assertTrue(parse_deposit_equity_response("Customer has sufficient equity on deposit."))
        self.assertTrue(parse_deposit_equity_response("Deposit balance meets the required threshold."))

    @patch("requests.post")
    def test_verify_deposit_equity_insufficient(self, mock_post):
        """Verify that verify_deposit_equity returns False when deposit agent returns meets_minimum: false."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": "equity-check-req",
            "result": {
                "artifacts": [
                    {
                        "parts": [{"text": '{"meets_minimum": false}'}]
                    }
                ]
