# Pure Live Remote

Pure Live Remote is a Docker-first remote live-stream resolver and M3U service derived from the platform-adapter concepts used by [Pure Live](https://github.com/liuchuancong/pure_live). The target is a LAN/self-hosted service with a Web admin, stable M3U channel URLs, live metadata/media caching, and later on-demand 302/proxy playback resolution.

> Current status: **Phase 2 / Test branch**. Room management and media caching are implemented; platform playback resolvers are not yet verified or enabled.

## Branch policy

- `Test`: all new or unverified implementation work goes here first.
- `main`: only code that has passed Docker startup, health, admin, M3U and real platform playback validation may be promoted here.
- GitHub Actions runs Python tests plus a Docker smoke test on pushes to `Test` and pull requests targeting `main`.

## Phase 2 features

### SQLite room storage

Persistent database: `/data/pure_live_remote.db`.

Each room stores:

- stable internal UUID;
- platform + platform room ID;
- original room URL;
- streamer/display name and group;
- avatar source URL;
- current live cover URL;
- last successful live cover URL;
- normalized local logo path;
- current and last-live local cover paths;
- enabled/sort order;
- preferred quality/line;
- future playback mode (`auto`, `redirect`, `proxy`);
- latest known live status/error.

`platform + room_id` is unique so the same upstream room is not accidentally added twice.

### Web admin CRUD

Open:

```text
http://HOST:35455/admin
```

The current Test UI supports:

- add room;
- edit room;
- enable/disable room;
- set group/sort/play preferences;
- delete room;
- manually refresh avatar/cover cache;
- show normalized avatar and effective cover.

JSON endpoints are also available under `/api/rooms` and are documented at `/docs`.

> Phase 2 has no admin authentication yet. Keep the service on a trusted LAN until authentication is added.

## M3U media policy

Pure Live Remote keeps **channel avatar/logo** and **live cover/poster** as separate media concepts.

### Channel logo / streamer avatar

- Source: streamer/avatar returned by the platform or entered in the admin.
- Stable output: `/media/logo/{uuid}.png`.
- Normalized output: **256×256 PNG**, transparent background, circular crop.
- M3U attribute: `tvg-logo`.
- The same normalization rule is applied to every platform.
- If a real avatar has not been cached, the endpoint returns a normalized local placeholder instead of exposing a raw upstream image.

### Live cover / poster

- While live: `/media/cover/{uuid}` serves the validated current-session cover when available.
- When offline/replay/banned: the current-session pointer is cleared, but the **last successful live cover is preserved** and served instead.
- Temporary missing media never deletes the stored last-live cover.
- M3U attribute in the Test build: `tvg-cover`.

`M3U` does not define one universal poster attribute comparable to `tvg-logo`; `tvg-cover` is therefore treated as a compatibility extension. The local cover endpoint is stable even if a specific client ignores the attribute.

Example:

```m3u
#EXTM3U
#EXTINF:-1 tvg-id="..." tvg-name="主播A" tvg-logo="http://HOST:35455/media/logo/...png" tvg-cover="http://HOST:35455/media/cover/..." group-title="直播",主播A
http://HOST:35455/play/...
```

## Current playback status

`/play/{uuid}` exists as the stable M3U target but intentionally returns HTTP `501` in Phase 2. Real platform URL resolution starts in Phase 3 so an unverified resolver cannot be mistaken for a working channel.

Planned flow:

```text
IPTV / M3U app
      |
      +--> GET /playlist.m3u
      |       +--> SQLite room list
      |       +--> local circular avatar URL
      |       +--> current/last-live cover URL
      |
      +--> GET /play/{uuid}
              +--> resolve platform room
              +--> select quality / CDN
              +--> 302 when direct playback is safe
              +--> proxy when required headers/cookies would otherwise cause 403
```

## Run with Docker Compose

```bash
cp .env.example .env
# Set PUBLIC_BASE_URL to the Docker host LAN address.
docker compose up -d --build
```

Default endpoints:

- Admin: `http://HOST:35455/admin`
- Health: `http://HOST:35455/health`
- M3U: `http://HOST:35455/playlist.m3u`
- OpenAPI: `http://HOST:35455/docs`

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `TZ` | `Asia/Shanghai` | Container timezone |
| `PORT` | `35455` | HTTP listen port |
| `PUBLIC_BASE_URL` | request host / compose fallback | Base URL written into M3U/media/play links |
| `DATA_DIR` | `/data` | SQLite and persistent media root |

## Test-branch validation

GitHub Actions performs:

1. Python unit tests for SQLite CRUD, M3U media attributes, cover fallback and circular-avatar normalization.
2. Docker image build.
3. Container startup and `/health` probe.
4. `/playlist.m3u` smoke check.
5. `/admin` smoke check.

## Next milestone: Phase 3

1. Port Bilibili room metadata/play-quality/play-URL logic first.
2. Automatically populate streamer name/avatar/current cover from the room URL/ID.
3. Implement `/play/{uuid}` live URL resolution with short cache.
4. Validate direct 302 playback.
5. Add header-aware proxy fallback for 403-prone streams.
6. After Bilibili acceptance, repeat the adapter process for Douyin, Douyu and Huya.

## License

Pure Live Remote is intended to reuse or adapt code/logic from Pure Live, which is licensed under AGPL-3.0. Code copied or adapted from that project must retain the corresponding license obligations and attribution.
