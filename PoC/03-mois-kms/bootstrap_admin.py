"""Create the first MoIS KMS administrator in the shared MinsLab Supabase project."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from env_utils import load_project_env  # noqa: E402

load_project_env(ROOT_DIR / ".env")

import backend  # noqa: E402


def main() -> int:
    try:
        existing_admins = backend._service_select(
            "user_roles",
            {"select": "user_id", "role": "eq.admin", "limit": "1"},
        )
    except backend.MoisKMSError as error:
        print(f"KMS 테이블을 확인하지 못했습니다: {error}")
        print("먼저 Supabase SQL Editor에서 20260710000000_minslab_kms.sql을 실행하세요.")
        return 1

    if existing_admins:
        print("이미 KMS 관리자가 존재합니다. 초기화 작업을 종료합니다.")
        return 0

    login_id = input("관리자 ID [admin]: ").strip() or "admin"
    name = input("관리자 이름 [관리자]: ").strip() or "관리자"
    password = getpass.getpass("관리자 비밀번호(6자 이상): ")
    confirm = getpass.getpass("관리자 비밀번호 확인: ")
    if password != confirm:
        print("비밀번호가 일치하지 않습니다.")
        return 1

    try:
        profiles = backend._service_select(
            "profiles",
            {"select": "id,login_id", "login_id": f"eq.{login_id}", "limit": "1"},
        )
        if profiles:
            user_id = profiles[0]["id"]
        else:
            backend.signup({
                "login_id": login_id,
                "password": password,
                "name": name,
                "position": "과장",
                "division_id": None,
                "team_id": None,
            })
            profiles = backend._service_select(
                "profiles",
                {"select": "id,login_id", "login_id": f"eq.{login_id}", "limit": "1"},
            )
            if not profiles:
                raise backend.MoisKMSError("생성한 관리자 프로필을 찾지 못했습니다.", 502)
            user_id = profiles[0]["id"]

        backend._request_json(
            "PATCH",
            backend._rest_path("profiles", {"id": f"eq.{user_id}"}),
            headers=backend._service_headers("return=minimal"),
            payload={"name": name, "position": "과장", "status": "승인", "team_id": None},
        )
        backend._service_insert("user_roles", {"user_id": user_id, "role": "admin"})
    except backend.MoisKMSError as error:
        print(f"관리자 초기화 실패: {error}")
        return 1

    print(f"KMS 관리자 '{login_id}' 계정을 생성하고 승인했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
