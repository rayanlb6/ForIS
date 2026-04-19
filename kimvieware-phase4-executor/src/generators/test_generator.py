from pathlib import Path
from typing import List, Dict
import re

from kimvieware_shared.models import Trajectory


# ============================================================
# SIMPLE ENDPOINT DETECTION (robuste et stable)
# ============================================================
def detect_endpoint(text: str) -> str:
    text = text.lower()

    if any(k in text for k in ["register", "signup", "create_user"]):
        return "register"
    if any(k in text for k in ["login", "signin", "auth"]):
        return "login"
    if "verify" in text or "token" in text:
        return "verify"

    return "login"


# ============================================================
# OUTCOME DETECTION
# ============================================================
def is_success(text: str) -> bool:
    text = text.lower()

    failure_keywords = [
        "error", "fail", "invalid", "wrong",
        "duplicate", "missing", "unauthorized"
    ]

    return not any(k in text for k in failure_keywords)


# ============================================================
# INPUT BUILDER (heuristique simple mais fiable)
# ============================================================
def build_inputs(endpoint: str, i: int) -> Dict:

    if endpoint == "register":
        return {
            "email": f"user{i}@mail.com",
            "username": f"user{i}",
            "password": "Test12345A!",
            "full_name": f"User {i}"
        }

    if endpoint == "login":
        return {
            "username": f"user{i}",
            "password": "Test12345A!"
        }

    if endpoint == "verify":
        return {
            "token": "valid_token"
        }

    return {}

# ============================================================
# TEST GENERATOR PRINCIPAL
# ============================================================
class TestGenerator:

    def generate(self, trajectories: List[Trajectory], output_dir: Path) -> Path:

        # 🔥 IMPORTANT: dossier stable (PAS /tmp)
        output_dir = Path("output/tests")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / "test_generated.py"

        print("\n==============================")
        print("🧪 TEST GENERATION START")
        print("==============================")
        print(f"📦 Trajectories received: {len(trajectories)}")
        print(f"📁 Output file: {output_file.resolve()}")

        if not trajectories:
            raise ValueError("❌ No trajectories provided to TestGenerator")

        code = """import requests

BASE_URL = "http://localhost:8000"

"""

        # ====================================================
        # GENERATION
        # ====================================================
        for i, traj in enumerate(trajectories):

            text = traj.path_condition + " " + " ".join(traj.branches_covered)

            endpoint = detect_endpoint(text)
            success = is_success(text)
            inputs = build_inputs(text, i)

            test_name = f"test_{traj.path_id}_{endpoint}_{i}"
            test_name = re.sub(r'[^a-zA-Z0-9_]', '_', test_name)

            code += f"\ndef {test_name}():\n"
            code += f"    # path_condition: {traj.path_condition}\n"

            # -------------------------
            # REQUEST
            # -------------------------
            if endpoint == "register":
                code += f"    response = requests.post(f\"{{BASE_URL}}/auth/register\", json={inputs})\n"

            elif endpoint == "login":
                code += f"    response = requests.post(f\"{{BASE_URL}}/auth/login\", json={inputs})\n"

            elif endpoint == "verify":
                token = inputs.get("token", "invalid_token")
                code += f"    response = requests.post(f\"{{BASE_URL}}/auth/verify?token={token}\")\n"

            # -------------------------
            # ASSERTIONS
            # -------------------------
            if success:
                code += "    assert response.status_code in [200, 201]\n"
            else:
                code += "    assert response.status_code in [400, 401, 403, 422]\n"

            code += "\n"

        # ====================================================
        # WRITE FILE
        # ====================================================
        output_file.write_text(code)

        print("\n==============================")
        print("✅ TESTS GENERATED SUCCESSFULLY")
        print(f"👉 FILE: {output_file.resolve()}")
        print("==============================\n")

        return output_file