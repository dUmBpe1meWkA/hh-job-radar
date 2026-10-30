from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import httpx

from config import config
from db import Database

HH_BASE = "https://api.hh.ru"
HH_TOKEN_URL = "https://api.hh.ru/token"
HH_AUTH_URL = "https://hh.ru/oauth/authorize"


class HHApiError(Exception):
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"HH API error {status_code}: {payload}")


class HHClient:
    def __init__(self, db: Database):
        self.db = db
        self.headers = {
            "User-Agent": config.hh_user_agent,
            "HH-User-Agent": config.hh_user_agent,
            "Accept": "application/json",
        }

    def auth_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": config.hh_client_id,
            "redirect_uri": config.hh_redirect_uri,
            "state": state,
        }
        return f"{HH_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "client_id": config.hh_client_id,
            "client_secret": config.hh_client_secret,
            "redirect_uri": config.hh_redirect_uri,
            "code": code,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(HH_TOKEN_URL, data=data, headers=self.headers)
        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            raise HHApiError(response.status_code, payload)
        expires_at = int(time.time()) + int(payload.get("expires_in", 0)) - 60
        self.db.set_token(payload["access_token"], payload["refresh_token"], expires_at)
        return payload

    async def refresh_token_if_needed(self) -> str | None:
        row = self.db.get_token()
        if not row:
            return None
        if row["expires_at"] and int(row["expires_at"]) > int(time.time()) + 60:
            return row["access_token"]

        data = {
            "grant_type": "refresh_token",
            "refresh_token": row["refresh_token"],
            "client_id": config.hh_client_id,
            "client_secret": config.hh_client_secret,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(HH_TOKEN_URL, data=data, headers=self.headers)
        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            raise HHApiError(response.status_code, payload)
        expires_at = int(time.time()) + int(payload.get("expires_in", 0)) - 60
        self.db.set_token(payload["access_token"], payload["refresh_token"], expires_at)
        return payload["access_token"]

    async def search_vacancies(self, text: str, page: int = 0) -> dict[str, Any]:
        params = {
            "text": text,
            "area": config.area,
            "page": page,
            "per_page": config.per_page,
            "period": config.publication_period_days,
            "order_by": "publication_time",
            "experience": "noExperience",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{HH_BASE}/vacancies", params=params, headers=self.headers)
        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            raise HHApiError(response.status_code, payload)
        return payload

    async def get_vacancy(self, vacancy_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{HH_BASE}/vacancies/{vacancy_id}", headers=self.headers)
        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            raise HHApiError(response.status_code, payload)
        return payload

    async def apply(self, vacancy_id: str, resume_id: str, message: str) -> dict[str, Any]:
        token = await self.refresh_token_if_needed()
        if not token:
            raise HHApiError(401, {"error": "not_authorized", "description": "Сначала выполните /auth"})

        headers = dict(self.headers)
        headers["Authorization"] = f"Bearer {token}"

        data = {
            "vacancy_id": str(vacancy_id),
            "resume_id": str(resume_id),
            "message": message,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{HH_BASE}/negotiations", data=data, headers=headers)

        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            raise HHApiError(response.status_code, payload)
        return payload

    async def get_me(self) -> dict[str, Any]:
        token = await self.refresh_token_if_needed()
        if not token:
            raise HHApiError(401, {"error": "not_authorized"})
        headers = dict(self.headers)
        headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{HH_BASE}/me", headers=headers)
        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            raise HHApiError(response.status_code, payload)
        return payload
