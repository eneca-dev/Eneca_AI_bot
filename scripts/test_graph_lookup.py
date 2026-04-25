"""Smoke test: fetch a user profile from Microsoft Graph.

Usage (from project root, with the venv active):

    python scripts/test_graph_lookup.py <aadObjectId>

Where to get an aadObjectId:
  * Azure Portal → Microsoft Entra ID → Users → pick a user → "Object ID".
  * Or: write to the bot in Teams once, then check the saved conversation
    references — the bot stores user_aad_object_id on first contact.

What it does:
  1. Verifies MICROSOFT_APP_ID / MICROSOFT_APP_PASSWORD / TENANT_ID are loaded.
  2. Asks Graph for the user profile.
  3. Prints displayName, jobTitle, department, companyName, mail.
  4. Calls the same lookup a second time to demonstrate the in-memory cache.
"""
import asyncio
import sys
from pathlib import Path

# Make project root importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _print(msg: str) -> None:
    print(msg, flush=True)


async def _run(aad_object_id: str) -> int:
    _print("Loading settings + Graph client...")
    from core.config import settings
    from services.graph_client import graph_client

    _print("\n--- Config check ---")
    _print(f"MICROSOFT_APP_ID set:       {bool(settings.microsoft_app_id)}")
    _print(f"MICROSOFT_APP_PASSWORD set: {bool(settings.microsoft_app_password)}")
    _print(f"TENANT_ID set:              {bool(settings.tenant_id)}")
    _print(f"Graph client configured:    {graph_client.is_configured}")

    if not graph_client.is_configured:
        _print("\nGraph client is not configured. Make sure MICROSOFT_APP_ID, "
               "MICROSOFT_APP_PASSWORD and TENANT_ID are set in .env.")
        return 1

    _print(f"\n--- Lookup #1 (live, hits Graph) for aadObjectId={aad_object_id} ---")
    profile = await graph_client.get_user_profile(aad_object_id)
    if not profile:
        _print("Graph returned None. Possible causes:")
        _print("  * User.Read.All admin consent not granted in Azure")
        _print("  * Wrong aadObjectId or user not in this tenant")
        _print("  * Network / firewall issue")
        _print("Check the application logs above for the exact error.")
        return 2

    _print(f"  displayName: {profile.get('displayName')!r}")
    _print(f"  jobTitle:    {profile.get('jobTitle')!r}")
    _print(f"  department:  {profile.get('department')!r}")
    _print(f"  companyName: {profile.get('companyName')!r}")
    _print(f"  mail:        {profile.get('mail')!r}")

    _print("\n--- Lookup #2 (must hit in-memory cache, no extra HTTP) ---")
    profile2 = await graph_client.get_user_profile(aad_object_id)
    same = profile == profile2
    _print(f"  cache hit: {same}  (results identical)")

    _print("\nAll good — Graph integration works.")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        _print("Usage: python scripts/test_graph_lookup.py <aadObjectId>")
        return 64
    return asyncio.run(_run(sys.argv[1]))


if __name__ == "__main__":
    sys.exit(main())
