import unittest
import json
import sqlite3
import database
import app as flask_app
from detector import combine_signals, evaluate_stylometric_signal

class ProvenanceGuardTestCase(unittest.TestCase):

    def setUp(self):
        # Configure app for testing
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['RATELIMIT_ENABLED'] = False
        flask_app.limiter.reset()
        
        # Use an in-memory SQLite database or a test database file for isolated tests
        self.test_db = "test_provenance_guard.db"
        flask_app.app.config['DATABASE_PATH'] = self.test_db
        
        # Override default database paths in database and flask_app
        database.DEFAULT_DB_PATH = self.test_db
        # Re-initialize the test database
        database.init_db(self.test_db)
        
        self.client = flask_app.app.test_client()

    def tearDown(self):
        # Clean up database file
        import os
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except OSError:
                pass

    def test_submit_validation(self):
        # Missing body
        response = self.client.post('/submit', json=None)
        self.assertEqual(response.status_code, 400)
        
        # Missing text
        response = self.client.post('/submit', json={"creator_id": "test-user"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("text", response.get_json()["message"])

        # Missing creator_id
        response = self.client.post('/submit', json={"text": "Some text"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("creator_id", response.get_json()["message"])

    def test_stylometric_heurstics(self):
        # Test clear human text (should have high sentence length variance, low uniformity)
        human_text = (
            "Wait. What? No way! I just saw a dog riding a skateboard down the street, "
            "and it was actually doing tricks! Unbelievable. I stood there, jaw dropped, "
            "staring for what felt like an hour but was probably only thirty seconds, "
            "while my coffee slowly went cold in my hand. Then, suddenly, it barked, "
            "hopped off the board, and ran towards its owner who was laughing hysterically. "
            "What a day. I guess you see something new every day, especially in this "
            "crazy city where normal rules of reality don't seem to apply."
        )
        # Test clear AI text (highly uniform sentence lengths and standard vocabulary distribution)
        ai_text = (
            "Artificial intelligence represents a transformative paradigm shift in modern society. "
            "The development of these systems should prioritize transparency and accountability. "
            "Machine learning algorithms can improve efficiency in healthcare and education. "
            "However, the potential for bias in training data remains a critical concern. "
            "Consequently, regulatory frameworks must be established to govern the use of these technologies. "
            "Ultimately, the successful integration of AI will depend on our ability to balance innovation. "
            "By fostering dialogue among scientists, we can create a future where technology serves the good. "
            "This approach will ensure that society benefits from these tools in the long term."
        )
        
        human_styl_score = evaluate_stylometric_signal(human_text)
        ai_styl_score = evaluate_stylometric_signal(ai_text)
        
        # AI stylometric score should be higher (indicating higher uniformity/AI likelihood)
        # than human stylometric score
        self.assertGreater(ai_styl_score, human_styl_score)

    def test_submit_flow_and_log(self):
        sample_text = "This is a sample human creative writing text of sufficient length."
        response = self.client.post('/submit', json={
            "text": sample_text,
            "creator_id": "creator-1"
        })
        self.assertEqual(response.status_code, 200)
        res_data = response.get_json()
        
        self.assertIn("content_id", res_data)
        self.assertIn("attribution", res_data)
        self.assertIn("confidence", res_data)
        self.assertIn("label", res_data)
        
        content_id = res_data["content_id"]
        
        # Verify db persistence
        sub = database.get_submission(content_id, self.test_db)
        self.assertIsNotNone(sub)
        self.assertEqual(sub["creator_id"], "creator-1")
        self.assertEqual(sub["status"], "classified")

        # Verify audit log retrieval
        log_response = self.client.get('/log')
        self.assertEqual(log_response.status_code, 200)
        logs = log_response.get_json()["entries"]
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]["content_id"], content_id)
        self.assertEqual(logs[0]["event_type"], "submission")

    def test_appeal_flow(self):
        # Submit a draft
        response = self.client.post('/submit', json={
            "text": "Draft content text for testing the appeal flow.",
            "creator_id": "creator-2"
        })
        content_id = response.get_json()["content_id"]
        
        # Appeal the classification
        appeal_response = self.client.post('/appeal', json={
            "content_id": content_id,
            "creator_reasoning": "I wrote this manually from personal journals."
        })
        self.assertEqual(appeal_response.status_code, 200)
        self.assertEqual(appeal_response.get_json()["status"], "under_review")
        
        # Verify status in database
        sub = database.get_submission(content_id, self.test_db)
        self.assertEqual(sub["status"], "under_review")
        self.assertEqual(sub["appeal_reasoning"], "I wrote this manually from personal journals.")
        
        # Verify appeal was logged in audit_log
        log_response = self.client.get('/log')
        logs = log_response.get_json()["entries"]
        
        # The latest log entry should be the appeal
        self.assertEqual(logs[0]["event_type"], "appeal")
        self.assertEqual(logs[0]["content_id"], content_id)
        self.assertEqual(logs[0]["appeal_reasoning"], "I wrote this manually from personal journals.")

    def test_appeal_invalid_id(self):
        response = self.client.post('/appeal', json={
            "content_id": "non-existent-uuid",
            "creator_reasoning": "Should fail"
        })
        self.assertEqual(response.status_code, 404)

    def test_rate_limiting(self):
        # Submit 10 rapidly inside test client
        flask_app.app.config['RATELIMIT_ENABLED'] = True
        flask_app.limiter.reset()
        
        try:
            # Let's perform 11 requests
            for i in range(12):
                response = self.client.post('/submit', json={
                    "text": "Rate limit spam test.",
                    "creator_id": "limiter-user"
                })
                if i >= 10:
                    self.assertEqual(response.status_code, 429)
                    self.assertIn("Rate limit exceeded", response.get_json()["message"])
                    break
        finally:
            flask_app.app.config['RATELIMIT_ENABLED'] = False

if __name__ == '__main__':
    unittest.main()
