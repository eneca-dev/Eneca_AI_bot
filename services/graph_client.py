"""Microsoft Graph client.

Used to enrich the Author block of a meeting protocol with the user's
job title, organization and department — fields that the Bot Framework
activity does not include.

Auth: client_credentials (same MICROSOFT_APP_ID / MICROSOFT_APP_PASSWORD as
Bot Framework, but token requested with the Graph scope). Requires the
`User.Read.All` Application permission on the Azure App Registration with
admin consent granted.

Fails open: missing config or Graph errors → `None`. Author rendering
falls back to whatever it had before (name only).
"""
import time
from typing import Optional, Dict, Any

import httpx
from loguru import logger

from core.config import settings


class GraphClient:
    """Singleton client for Microsoft Graph user-profile lookups."""

    OAUTH_SCOPE = "https://graph.microsoft.com/.default"
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    PROFILE_FIELDS = "displayName,jobTitle,department,companyName,mail"
    PROFILE_TTL_SECONDS = 30 * 60  # 30 minutes

    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        # cache: aad_object_id -> (profile_dict, fetched_at_ts)
        self._profile_cache: Dict[str, tuple] = {}
        logger.info("GraphClient initialized")

    @property
    def is_configured(self) -> bool:
        return bool(
            settings.microsoft_app_id
            and settings.microsoft_app_password
            and settings.tenant_id
        )

    async def _get_token(self) -> str:
        """Get an OAuth token for Microsoft Graph (cached until close to expiry)."""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        if not self.is_configured:
            raise ValueError(
                "Microsoft Graph requires MICROSOFT_APP_ID, MICROSOFT_APP_PASSWORD "
                "and TENANT_ID in .env"
            )

        oauth_url = (
            f"https://login.microsoftonline.com/{settings.tenant_id}/oauth2/v2.0/token"
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                oauth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.microsoft_app_id,
                    "client_secret": settings.microsoft_app_password,
                    "scope": self.OAUTH_SCOPE,
                },
            )
            if response.status_code != 200:
                logger.error(
                    f"Graph OAuth failed: {response.status_code} {response.text}"
                )
                response.raise_for_status()
            data = response.json()

        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        logger.info("Microsoft Graph OAuth token acquired")
        return self._token

    def _cached_profile(self, aad_object_id: str) -> Optional[Dict[str, Any]]:
        cached = self._profile_cache.get(aad_object_id)
        if not cached:
            return None
        data, fetched_at = cached
        if time.time() - fetched_at >= self.PROFILE_TTL_SECONDS:
            return None
        return data

    async def get_user_profile(self, aad_object_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Fetch a user profile by AAD Object ID. Returns None on any failure."""
        if not aad_object_id:
            return None

        if not self.is_configured:
            logger.debug(
                f"GraphClient not configured — skipping profile lookup for {aad_object_id}"
            )
            return None

        cached = self._cached_profile(aad_object_id)
        if cached is not None:
            return cached

        try:
            token = await self._get_token()
            url = f"{self.GRAPH_BASE}/users/{aad_object_id}"
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params={"$select": self.PROFILE_FIELDS},
                    headers={"Authorization": f"Bearer {token}"},
                )
            if response.status_code == 404:
                logger.warning(f"Graph: user {aad_object_id} not found")
                return None
            if response.status_code == 403:
                logger.error(
                    f"Graph: forbidden for user {aad_object_id} — "
                    "check User.Read.All admin consent in Azure"
                )
                return None
            response.raise_for_status()

            raw = response.json()
            profile = {
                "displayName": raw.get("displayName"),
                "jobTitle": raw.get("jobTitle"),
                "department": raw.get("department"),
                "companyName": raw.get("companyName"),
                "mail": raw.get("mail"),
            }
            self._profile_cache[aad_object_id] = (profile, time.time())
            logger.info(
                f"Graph profile fetched: aad={aad_object_id}, "
                f"jobTitle={profile['jobTitle']!r}, "
                f"companyName={profile['companyName']!r}, "
                f"department={profile['department']!r}"
            )
            return profile

        except Exception as e:
            logger.error(f"Failed to fetch Graph profile for {aad_object_id}: {e}")
            return None


graph_client = GraphClient()
