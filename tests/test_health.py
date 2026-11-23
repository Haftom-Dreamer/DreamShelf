import unittest
from main import app


class HealthCheckTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def test_health_endpoint_success(self):
        """Test that /health returns HTTP 200 and expected JSON payload."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        data = response.get_json()
        self.assertEqual(data, {"status": "healthy"})

    def test_health_endpoint_post_not_allowed(self):
        """Test that /health only accepts GET requests."""
        response = self.client.post("/health")
        self.assertEqual(response.status_code, 405)

    def test_health_no_auth_required(self):
        """Test that /health is public and does not redirect to login."""
        response = self.client.get("/health", follow_redirects=False)
        self.assertEqual(response.status_code, 200)

    def test_existing_landing_route(self):
        """Ensure core routes like landing page still respond properly."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()

