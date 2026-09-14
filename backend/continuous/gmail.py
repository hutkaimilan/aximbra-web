"""A Gmail-oldal: friss hozzáférés a tárolt tokenből, és a két lekérdezés,
amit a futás használ.

Külön fájlban, mert a `worker` logikája így hálózat nélkül tesztelhető: a
futásnak elég egy objektum, ami tudja a `list_since`, `list_new` és `fetch`
hívásokat — hogy mögötte a Google van vagy egy csonk, azt nem kell tudnia.

Olvasásra kapott jog, és ez itt is kódszinten igaz: a `SafeGmailProxy` a
küldést elutasítja, és ez a modul soha nem kér írási hatókört.
"""
import asyncio
import logging
import os

import httplib2
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

TOKEN_URI = "https://oauth2.googleapis.com/token"
READONLY = ["https://www.googleapis.com/auth/gmail.readonly"]
HTTP_TIMEOUT_SECONDS = 30


def _fresh_http(creds):
    """Szálanként külön HTTP: az httplib2 nem szálbiztos, és a levelek
    párhuzamosan töltődnek."""
    return AuthorizedHttp(creds, http=httplib2.Http(timeout=HTTP_TIMEOUT_SECONDS))


def credentials_from_refresh_token(refresh_token: str) -> Credentials:
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        scopes=READONLY,
    )


class GmailMailbox:
    """Egy fiók postaládája. A hívások szinkronok a Google könyvtárában,
    ezért mind külön szálon futnak — különben egy futás megállítaná az egész
    kiszolgálót."""

    def __init__(self, refresh_token: str, safe_proxy=None):
        self._creds = credentials_from_refresh_token(refresh_token)
        self._proxy = safe_proxy
        self._service = None

    async def _svc(self):
        if self._service is None:
            svc = await asyncio.to_thread(build, "gmail", "v1", credentials=self._creds)
            self._service = self._proxy(svc) if self._proxy else svc
        return self._service

    async def list_since(self, query: str, limit: int):
        """Első futás: minden levél a megadott időszakból, és a mostani
        `historyId`, hogy a következő futás onnan folytassa."""
        svc = await self._svc()
        listing = await asyncio.to_thread(
            svc.users().messages().list(userId="me", maxResults=limit, q=query).execute,
            http=_fresh_http(self._creds),
        )
        profile = await asyncio.to_thread(
            svc.users().getProfile(userId="me").execute, http=_fresh_http(self._creds)
        )
        return [m["id"] for m in listing.get("messages", [])], str(profile.get("historyId") or "")

    async def list_new(self, history_id: str, limit: int):
        """Csak ami a megadott pont óta érkezett.

        Ha a Gmail szerint a `historyId` már túl régi (a Google véges ideig
        tartja a történetet), teljes lekérdezésre esünk vissza — inkább
        fussunk egy kört fölöslegesen, mint hogy csendben kimaradjon egy hét.
        """
        svc = await self._svc()
        try:
            resp = await asyncio.to_thread(
                svc.users().history().list(
                    userId="me", startHistoryId=history_id,
                    historyTypes=["messageAdded"], maxResults=limit,
                ).execute,
                http=_fresh_http(self._creds),
            )
        except Exception as e:  # noqa - 404: elavult historyId
            logger.info("continuous: history unusable (%s), full pass instead", type(e).__name__)
            from .worker import backfill_query  # noqa: körkörös csak futásidőben

            return await self.list_since(backfill_query(months=1), limit)

        ids = []
        for h in resp.get("history", []):
            for added in h.get("messagesAdded", []):
                mid = (added.get("message") or {}).get("id")
                if mid and mid not in ids:
                    ids.append(mid)
        return ids[:limit], str(resp.get("historyId") or history_id)

    async def fetch(self, message_id: str) -> dict:
        from mail_agent import _parse  # noqa: a feldolgozás egy helyen lakik

        svc = await self._svc()
        msg = await asyncio.to_thread(
            svc.users().messages().get(userId="me", id=message_id, format="full").execute,
            http=_fresh_http(self._creds),
        )
        return _parse(msg)
