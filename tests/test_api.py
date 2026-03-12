"""Integration tests for API endpoints (without database)."""
import pytest
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "revozi-api"


class TestAuthEndpoints:
    def test_login_without_body(self):
        response = client.post("/api/v1/auth/login")
        assert response.status_code == 422  # Validation error

    def test_signup_without_body(self):
        response = client.post("/api/v1/auth/signup")
        assert response.status_code == 422

    def test_logout(self):
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 200
        assert response.json()["message"] == "Logged out"

    def test_refresh_without_cookie(self):
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    def test_forgot_password(self):
        response = client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
        assert response.status_code == 200


class TestProtectedEndpoints:
    def test_me_without_auth(self):
        response = client.get("/api/v1/users/me")
        assert response.status_code == 403  # No Bearer token

    def test_workspaces_without_auth(self):
        response = client.get("/api/v1/workspaces")
        assert response.status_code == 403

    def test_admin_without_auth(self):
        response = client.get("/api/v1/admin/metrics")
        assert response.status_code == 403
