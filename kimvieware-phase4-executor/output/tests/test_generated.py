import requests

BASE_URL = "http://localhost:8000"


def test_java_validateUsername_path_000_login_0():
    # path_condition: validateUsername_path_0
    response = requests.post(f"{BASE_URL}/auth/login", json={'username': 'user0'})
    assert response.status_code in [200, 201]

