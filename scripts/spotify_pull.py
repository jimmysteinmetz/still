"""One-off pull of your Spotify top artists/genres to bias Shows + Music news.

WHY: the Music & Shows section and the almanac Shows card currently surface
artists the user doesn't recognize. Both are configured by hand
(``almanac.shows.artists`` and the music line under ``interests`` in
``config/still.yaml``) — this script just gathers real listening data so those
lists can be re-curated toward artists actually listened to. It is a ONE-OFF,
manual tool, not a pipeline stage: nothing in ``still build`` calls it, and it
adds no dependency to the daily run. Re-run it by hand whenever listening
habits drift (every few months is plenty).

SETUP (one time):
    1. Create an app at https://developer.spotify.com/dashboard
    2. In the app's settings, add this exact redirect URI:
           http://127.0.0.1:8888/callback
    3. Copy the app's Client ID (and, optionally, Client Secret — see below)
       into your ``.env`` (copy ``.env.example`` if you haven't already):
           SPOTIFY_CLIENT_ID=...
           SPOTIFY_CLIENT_SECRET=...   # optional, see below

AUTH: this uses the Authorization Code flow with PKCE (RFC 7636), which is
required here because personal top-artists data needs USER auth — the
Client Credentials flow (app-only, no user) can't see it. PKCE makes
SPOTIFY_CLIENT_SECRET optional: a "Client ID only" Spotify app works fine.
If SPOTIFY_CLIENT_SECRET *is* set, it's additionally sent as HTTP Basic auth
on the token exchange (harmless alongside PKCE); if it's unset, PKCE alone
authenticates the request. Scope requested: ``user-top-read`` (read-only).

RUN:
    uv run scripts/spotify_pull.py

This opens a browser tab for you to log in and approve access. A tiny local
HTTP server (stdlib ``http.server``, no persistent process) catches the
redirect on http://127.0.0.1:8888/callback, and the script exits after
printing its report — nothing is stored on disk, no daemon is left running.

OUTPUT: your top artists across Spotify's three time ranges (last ~4 weeks /
~6 months / several years), deduped and ranked by how consistently they show
up, then the same for genres, then a ready-to-paste YAML block for
``almanac.shows.artists`` and a suggested ``interests`` line — paste both into
``config/still.yaml`` by hand (this script never writes files).
"""

import base64
import hashlib
import os
import secrets
import sys
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv

REDIRECT_PORT = 8888
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
SCOPE = "user-top-read"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
TIME_RANGES = ("short_term", "medium_term", "long_term")
TOP_ARTISTS_LIMIT = 50  # Spotify's max page size for /me/top/artists
SUGGESTED_ARTIST_COUNT = 9  # matches the current almanac.shows.artists list size
SUGGESTED_GENRE_COUNT = 12

# (name, genres, appearances across the 3 time ranges, best 0-based rank position)
RankedArtist = tuple[str, list[str], int, int]


class _CallbackHandler(BaseHTTPRequestHandler):
    """Captures the ``?code=`` (or ``?error=``) query param from the OAuth redirect."""

    result: dict[str, str] = {}  # class-level: written by the single request we handle

    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        if "code" in query:
            _CallbackHandler.result["code"] = query["code"][0]
            body = b"<html><body>Authorized \xe2\x80\x94 you can close this tab.</body></html>"
        else:
            _CallbackHandler.result["error"] = query.get("error", ["unknown_error"])[0]
            body = (
                b"<html><body>Authorization failed \xe2\x80\x94 check the terminal.</body></html>"
            )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return  # silence default per-request logging to stderr


def _make_pkce_pair() -> tuple[str, str]:
    """Random ``code_verifier`` + its S256 ``code_challenge``, per RFC 7636."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _authorize(client_id: str) -> tuple[str, str]:
    """Open the browser for consent; block until the local redirect delivers a code.

    Returns (authorization_code, pkce_code_verifier).
    """
    verifier, challenge = _make_pkce_pair()
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    print(f"\nOpening your browser for Spotify consent (scope: {SCOPE})...")
    print(f"If it doesn't open automatically, visit:\n  {url}\n")

    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    webbrowser.open(url)
    server.handle_request()  # blocks for exactly the one redirect hit, then returns
    server.server_close()

    result = _CallbackHandler.result
    if "error" in result:
        print(f"Spotify denied authorization: {result['error']}", file=sys.stderr)
        sys.exit(1)
    code = result.get("code")
    if not code:
        print("No authorization code received from Spotify.", file=sys.stderr)
        sys.exit(1)
    return code, verifier


def _exchange_code(client_id: str, client_secret: str | None, code: str, verifier: str) -> str:
    """Trade the authorization code for an access token."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    # PKCE alone authenticates the request; a client_secret (if configured) is sent
    # as ordinary HTTP Basic auth on top of that — supported either way.
    auth = (client_id, client_secret) if client_secret else None
    resp = httpx.post(TOKEN_URL, data=data, auth=auth, timeout=30)
    resp.raise_for_status()
    token: str = resp.json()["access_token"]
    return token


def _fetch_top_artists(token: str, time_range: str) -> list[dict[str, object]]:
    """One page (up to 50) of top artists for a single Spotify time range."""
    resp = httpx.get(
        f"{API_BASE}/me/top/artists",
        headers={"Authorization": f"Bearer {token}"},
        params={"time_range": time_range, "limit": TOP_ARTISTS_LIMIT},
        timeout=30,
    )
    resp.raise_for_status()
    items: list[dict[str, object]] = resp.json().get("items", [])
    return items


def _rank_artists(by_range: dict[str, list[dict[str, object]]]) -> list[RankedArtist]:
    """Dedupe artists seen across time ranges, best (most consistent) first.

    Ranked by (# time ranges the artist appears in, descending), then by the
    best 0-based position they held in any single range (ascending) — an
    artist near the top of even one range outranks one buried in all three.
    """
    best: dict[str, RankedArtist] = {}
    for artists in by_range.values():
        for position, artist in enumerate(artists):
            artist_id = str(artist["id"])
            name = str(artist["name"])
            raw_genres = artist.get("genres", [])
            genres = [str(g) for g in raw_genres] if isinstance(raw_genres, list) else []
            if artist_id in best:
                _, _, appearances, best_rank = best[artist_id]
                best[artist_id] = (name, genres, appearances + 1, min(best_rank, position))
            else:
                best[artist_id] = (name, genres, 1, position)
    return sorted(best.values(), key=lambda v: (-v[2], v[3]))


def _top_genres(ranked: list[RankedArtist], n: int) -> list[tuple[str, int]]:
    counts = Counter(genre for _name, genres, _appearances, _rank in ranked for genre in genres)
    return counts.most_common(n)


def _print_report(ranked: list[RankedArtist], genres: list[tuple[str, int]]) -> None:
    print("\n" + "=" * 78)
    print("SPOTIFY TOP ARTISTS  (deduped + ranked across short/medium/long_term)")
    print("=" * 78)
    for i, (name, artist_genres, appearances, rank) in enumerate(ranked[:25], start=1):
        genre_str = ", ".join(artist_genres[:3]) if artist_genres else "(no genre tags)"
        print(f"{i:>2}. {name}  [{genre_str}]  (in {appearances}/3 ranges, best #{rank + 1})")

    print("\n" + "=" * 78)
    print("TOP GENRES")
    print("=" * 78)
    for genre, count in genres:
        print(f"  {genre}  (x{count})")

    top_names = [name for name, _genres, _appearances, _rank in ranked[:SUGGESTED_ARTIST_COUNT]]
    print("\n" + "=" * 78)
    print("READY TO PASTE 1/2 — replace almanac.shows.artists in config/still.yaml:")
    print("=" * 78)
    print("    artists:")
    for name in top_names:
        print(f"      - {name}")

    genre_words = ", ".join(g for g, _count in genres[:6])
    artist_words = ", ".join(top_names[:6])
    print("\n" + "=" * 78)
    print("READY TO PASTE 2/2 — suggested replacement for the music line under interests:")
    print("=" * 78)
    print(
        f"  - {genre_words} — {artist_words} and affiliated acts; new releases and NYC-area shows"
    )
    print(
        "\nEdit config/still.yaml by hand with the blocks above — this script never "
        "writes files. Trim to artists/genres you'd actually recognize; fewer, "
        "better-known names beat a long list (the Shows card is already capped at "
        "max_rows, so curating *which* artists are configured is the real lever, "
        "not raising that cap).\n"
    )


def main() -> None:
    load_dotenv()
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    if not client_id:
        print(
            "SPOTIFY_CLIENT_ID is not set — nothing to do.\n\n"
            "This is a one-off script that pulls your Spotify top artists/genres to "
            "bias the Shows card + Music & Shows news toward artists you actually "
            "listen to. Full setup is in this file's module docstring; quick version:\n"
            "  1. Create an app at https://developer.spotify.com/dashboard\n"
            "  2. Add redirect URI http://127.0.0.1:8888/callback in its settings\n"
            "  3. Put SPOTIFY_CLIENT_ID=... (Client Secret optional — PKCE covers it)\n"
            "     in your .env (copy .env.example if you don't have one yet)\n"
            "  4. Re-run: uv run scripts/spotify_pull.py",
            file=sys.stderr,
        )
        sys.exit(1)
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET") or None

    code, verifier = _authorize(client_id)
    token = _exchange_code(client_id, client_secret, code, verifier)

    by_range: dict[str, list[dict[str, object]]] = {}
    for time_range in TIME_RANGES:
        try:
            by_range[time_range] = _fetch_top_artists(token, time_range)
        except httpx.HTTPError as e:
            print(f"Warning: couldn't fetch {time_range} top artists: {e}", file=sys.stderr)
            by_range[time_range] = []

    ranked = _rank_artists(by_range)
    if not ranked:
        print(
            "No top artists returned. Spotify needs more listening history to build "
            "this data, or the user-top-read scope wasn't granted.",
            file=sys.stderr,
        )
        sys.exit(1)

    genres = _top_genres(ranked, SUGGESTED_GENRE_COUNT)
    _print_report(ranked, genres)


if __name__ == "__main__":
    main()
