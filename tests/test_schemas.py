"""Unit tests for Pydantic schemas (UserIntent, AnswerResponse).

Tests both valid instances and invalid instances catching ValidationError.
Can be executed with:
    python test_schemas.py
or
    python -m unittest test_schemas.py
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from pydantic import ValidationError
from schemas import UserIntent, AnswerResponse


class TestSchemas(unittest.TestCase):
    """Test suite for schema validation and type constraints."""

    def test_valid_user_intent_qa(self):
        intent = UserIntent(intent_type="qa", confidence=0.95, reasoning="Inquiring about branch hours")
        self.assertEqual(intent.intent_type, "qa")
        self.assertAlmostEqual(intent.confidence, 0.95)

    def test_valid_user_intent_summarization(self):
        intent = UserIntent(intent_type="summarization", confidence=0.90, reasoning="Overview request")
        self.assertEqual(intent.intent_type, "summarization")
        self.assertAlmostEqual(intent.confidence, 0.90)

    def test_valid_user_intent_calculation(self):
        intent = UserIntent(intent_type="calculation", confidence=0.99, reasoning="Math evaluation")
        self.assertEqual(intent.intent_type, "calculation")
        self.assertAlmostEqual(intent.confidence, 0.99)

    def test_valid_answer_response(self):
        ans = AnswerResponse(
            response="Auto loan rates start at 4.5% APR.",
            confidence=0.96,
            sources=["bank_knowledge_base"],
            intent="qa",
            session_id="session-001"
        )
        self.assertEqual(ans.response, "Auto loan rates start at 4.5% APR.")
        self.assertAlmostEqual(ans.confidence, 0.96)
        self.assertIn("bank_knowledge_base", ans.sources)

    def test_invalid_confidence_negative(self):
        with self.assertRaises(ValidationError) as ctx:
            UserIntent(intent_type="qa", confidence=-0.5)
        self.assertTrue(any("greater than or equal to 0" in str(err) for err in ctx.exception.errors()))

    def test_invalid_confidence_exceeds_one(self):
        with self.assertRaises(ValidationError) as ctx:
            UserIntent(intent_type="qa", confidence=1.5)
        self.assertTrue(any("less than or equal to 1" in str(err) for err in ctx.exception.errors()))

    def test_invalid_intent_type(self):
        with self.assertRaises(ValidationError) as ctx:
            UserIntent(intent_type="chat", confidence=0.8)
        self.assertTrue(any("Input should be 'qa', 'summarization' or 'calculation'" in str(err) for err in ctx.exception.errors()))

    def test_invalid_answer_response_confidence(self):
        with self.assertRaises(ValidationError):
            AnswerResponse(response="Test", confidence=2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
