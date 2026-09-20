# Migration to AnimeWorld India

Migrate the anime scraping API from Animelok (defunct) to AnimeWorld India (`watchanimeworlds.com`). This includes updating the scraper, service layer, and maintaining "Full Potential" features (AniList mapping, Supabase persistence, Redis caching, and Proxy rotation).

## User Review Required

> [!IMPORTANT]
> The source site has changed from `animelok.online` to `watchanimeworlds.com`. The ID format for episodes and anime will change, but the API will still use AniList IDs as the primary public identifier.

> [!WARNING]
> Some advanced features like "Intro/Outro skip" and "Multi-Audio" depend on the source site's metadata. If the new source doesn't provide them for specific episodes, they will return empty values.

## Proposed Changes

### Configuration

#### [MODIFY] [config.py](file:///C:/Users/sanya/StudioProjects/AniLove-Animelok-Api/app/config.py)
- Update `base_url` to `https://watchanimeworlds.com`.
- Update `app_name` to `AnimeWorld India Scraper API`.

### Scrapers

#### [NEW] [animeworld.py](file:///C:/Users/sanya/StudioProjects/AniLove-Animelok-Api/app/scrapers/animeworld.py)
- Implement `AnimeworldScraper` using `selectolax` and `httpx`.
- Implement `search` (using `/?s=`), `info` (parsing series/movie pages), and `stream` (extracting video embeds).
- Handle WordPress-style pagination and grid layouts.

#### [DELETE] [animelok.py](file:///C:/Users/sanya/StudioProjects/AniLove-Animelok-Api/app/scrapers/animelok.py)
- Remove the defunct Animelok scraper.

### Services

#### [MODIFY] [anime_service.py](file:///C:/Users/sanya/StudioProjects/AniLove-Animelok-Api/app/services/anime_service.py)
- Replace `AnimelokScraper` with `AnimeworldScraper`.
- Update the mapping logic to handle new provider IDs.

### Models & Utils

#### [MODIFY] [parsers.py](file:///C:/Users/sanya/StudioProjects/AniLove-Animelok-Api/app/parsers.py)
- Update HTML parsing helpers to match the `watchanimeworlds.com` DOM structure.

## Verification Plan

### Automated Tests
- Run `pytest` if available (need to check for existing tests).
- Execute a scratch script to verify `search`, `info`, and `stream` endpoints locally before pushing.

### Manual Verification
- Test `/api/search?q=Solo+Leveling` to verify AniList results.
- Test `/api/info/{anilist_id}` to verify mapping and metadata extraction.
- Test `/api/stream/{anilist_id}?ep=1` to verify HLS link extraction.
