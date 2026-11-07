"""scripts/github_awesome_miner.py — Miner and curation engine for @GithubAwesome videos.

Extracts GitHub repositories featured across the @GithubAwesome channel,
deduplicates repository links, normalizes URLs, categorizes tools by capability,
scores relevance for native Ultron integration, and exports structured datasets.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure stdout handles UTF-8 on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    getattr(sys.stdout, "reconfigure", lambda **kw: None)(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = ROOT / "data" / "github_awesome_cache"
DEFAULT_OUTPUT_JSON = ROOT / "data" / "github_awesome_repos.json"
DEFAULT_CATALOG_MD = ROOT / "docs" / "GITHUB_AWESOME_CATALOG.md"
DEFAULT_CANDIDATES_MD = ROOT / "docs" / "ULTRON_INTEGRATION_CANDIDATES.md"

# GitHub URL extractor pattern
GITHUB_REPO_REGEX = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:[/?#\s]|$)",
    re.IGNORECASE,
)

# Reserved non-repository GitHub namespaces
EXCLUDED_GITHUB_USERS = {
    "sponsors", "features", "topics", "trending", "collections",
    "events", "explore", "pricing", "login", "join", "about",
    "site", "security", "contact", "customer-stories", "enterprise",
    "readme", "pulls", "issues", "settings", "orgs",
}

# Domain Category Keywords for Ultron Relevance
CATEGORIES = {
    "Voice & Speech": [
        "whisper", "tts", "stt", "speech", "voice", "audio", "sound",
        "piper", "kokoro", "chatterbox", "transcription", "asr", "synthesizer"
    ],
    "Vision & Multimodal": [
        "vision", "ocr", "camera", "multimodal", "yolo", "florence",
        "omniparser", "screen", "image", "video", "surya", "document", "pdf"
    ],
    "Agents & LLM Systems": [
        "agent", "llm", "rag", "langchain", "prompt", "reasoning",
        "autogen", "crew", "copilot", "chat", "tool", "workflow", "crawl4ai",
        "claude", "gpt", "gemini", "ollama", "localai", "vllm"
    ],
    "System Automation & OS": [
        "desktop", "automation", "mouse", "keyboard", "window", "process",
        "taskman", "gpu", "monitor", "system", "app", "browser-use", "os",
        "sshyard", "manager", "control"
    ],
    "Terminal, CLI & Dev Tools": [
        "terminal", "cli", "shell", "console", "tui", "debug",
        "rerun", "profiler", "git", "code", "editor", "compiler", "ast"
    ],
}


@dataclass
class VideoRecord:
    id: str
    title: str
    url: str
    description: str = ""
    duration: int = 0
    view_count: int = 0
    upload_date: str = ""


@dataclass
class RepoMention:
    owner: str
    repo: str
    full_name: str
    url: str
    video_id: str
    video_title: str
    context_line: str
    timestamp: str = ""


@dataclass
class RepoRecord:
    full_name: str
    owner: str
    repo: str
    url: str
    mentions_count: int
    categories: List[str] = field(default_factory=list)
    ultron_score: int = 0
    ultron_layer: str = ""
    featured_in: List[Dict[str, str]] = field(default_factory=list)
    sample_context: str = ""


def extract_repo_urls(text: str, video: VideoRecord) -> List[RepoMention]:
    """Parse text and extract all valid GitHub repository links with context."""
    results: List[RepoMention] = []
    seen_in_video: Set[str] = set()

    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        for match in GITHUB_REPO_REGEX.finditer(line_clean):
            owner = match.group(1).strip()
            repo = match.group(2).strip().rstrip(".,;:)'\"")

            if repo.endswith(".git"):
                repo = repo[:-4]

            if owner.lower() in EXCLUDED_GITHUB_USERS or not repo:
                continue

            full_name = f"{owner}/{repo}"
            if full_name.lower() in seen_in_video:
                continue
            seen_in_video.add(full_name.lower())

            # Detect timestamp if present (e.g. '01:24 - ')
            ts_match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", line_clean)
            timestamp = ts_match.group(1) if ts_match else ""

            # Extract human label before or after link
            clean_context = line_clean
            clean_context = re.sub(r"https?://\S+", "", clean_context).strip(" -:\t")

            mention = RepoMention(
                owner=owner,
                repo=repo,
                full_name=full_name,
                url=f"https://github.com/{owner}/{repo}",
                video_id=video.id,
                video_title=video.title,
                context_line=clean_context or repo,
                timestamp=timestamp,
            )
            results.append(mention)

    return results


def classify_repo(name: str, context: str) -> Tuple[List[str], int, str]:
    """Assign domain categories and compute Ultron relevance score (0-100)."""
    text_to_search = f"{name} {context}".lower()
    matched_cats: List[str] = []

    for cat_name, keywords in CATEGORIES.items():
        if any(kw in text_to_search for kw in keywords):
            matched_cats.append(cat_name)

    if not matched_cats:
        matched_cats.append("General Tools")

    # Score calculation
    score = 40  # base score
    layer = "General Utility"

    if "Agents & LLM Systems" in matched_cats:
        score += 35
        layer = "Layer 3 (Agent / Reasoning / Tool Use)"
    elif "Voice & Speech" in matched_cats:
        score += 35
        layer = "Layer 1 (Voice / Audio / STT / TTS)"
    elif "Vision & Multimodal" in matched_cats:
        score += 30
        layer = "Layer 2 (Vision / Multimodal / OCR)"
    elif "System Automation & OS" in matched_cats:
        score += 25
        layer = "Layer 4 (Actions & OS Control)"
    elif "Terminal, CLI & Dev Tools" in matched_cats:
        score += 20
        layer = "Layer 5 (Developer & CLI Tools)"

    return matched_cats, min(100, score), layer


class GithubAwesomeMiner:
    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.videos_cache_file = self.cache_dir / "videos.json"

    def fetch_channel_videos(self, channel_url: str = "https://www.youtube.com/@GithubAwesome/videos",
                             limit: Optional[int] = None) -> List[VideoRecord]:
        """Fetch list of videos from channel using yt-dlp flat extraction."""
        import yt_dlp

        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "skip_download": True,
            "playlist_items": f"1-{limit}" if limit else None,
        }

        print(f"[Miner] Extracting video list from {channel_url}...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            entries = info.get("entries", [])

        videos: List[VideoRecord] = []
        for entry in entries:
            vid = entry.get("id")
            title = entry.get("title", "")
            url = entry.get("url") or f"https://www.youtube.com/watch?v={vid}"
            if vid:
                videos.append(VideoRecord(
                    id=vid,
                    title=title,
                    url=url,
                    duration=entry.get("duration") or 0,
                    view_count=entry.get("view_count") or 0,
                    upload_date=entry.get("upload_date") or "",
                ))

        print(f"[Miner] Found {len(videos)} videos on channel.")
        return videos

    def populate_descriptions(self, videos: List[VideoRecord], max_workers: int = 8) -> List[VideoRecord]:
        """Fetch detailed descriptions for videos concurrently."""
        import yt_dlp

        # Check existing cache
        cached_data = {}
        if self.videos_cache_file.exists():
            try:
                cached_list = json.loads(self.videos_cache_file.read_text(encoding="utf-8"))
                for v in cached_list:
                    cached_data[v["id"]] = v
            except Exception:
                cached_data = {}

        to_fetch: List[VideoRecord] = []
        populated: List[VideoRecord] = []

        for v in videos:
            if v.id in cached_data and cached_data[v.id].get("description"):
                cached_v = cached_data[v.id]
                v.description = cached_v["description"]
                populated.append(v)
            else:
                to_fetch.append(v)

        print(f"[Miner] {len(populated)} videos loaded from cache. Fetching descriptions for {len(to_fetch)} videos...")

        if not to_fetch:
            return populated

        ydl_opts = {
            "skip_download": True,
            "quiet": True,
        }

        def _fetch_one(vid: VideoRecord) -> VideoRecord:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(vid.url, download=False)
                    vid.description = info.get("description", "")
            except Exception as e:
                print(f"[Miner] Warning: failed to fetch {vid.id}: {e}")
            return vid

        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch_one, v) for v in to_fetch]
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                populated.append(res)
                completed += 1
                if completed % 25 == 0 or completed == len(to_fetch):
                    print(f"[Miner] Fetched descriptions: {completed}/{len(to_fetch)}")

        # Save cache
        self.save_video_cache(populated)
        return populated

    def save_video_cache(self, videos: List[VideoRecord]) -> None:
        data = [asdict(v) for v in videos]
        self.videos_cache_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[Miner] Cached {len(videos)} videos to {self.videos_cache_file}")

    def mine_repositories(self, videos: List[VideoRecord]) -> List[RepoRecord]:
        """Extract all GitHub repos, deduplicate, score, and group mentions."""
        raw_mentions: List[RepoMention] = []

        for video in videos:
            if video.description:
                mentions = extract_repo_urls(video.description, video)
                raw_mentions.extend(mentions)

        print(f"[Miner] Extracted {len(raw_mentions)} total raw repository mentions across all videos.")

        # Group and deduplicate
        by_repo: Dict[str, List[RepoMention]] = {}
        for m in raw_mentions:
            key = m.full_name.lower()
            by_repo.setdefault(key, []).append(m)

        records: List[RepoRecord] = []
        for key, mentions in by_repo.items():
            first = mentions[0]
            context = " | ".join(dict.fromkeys(m.context_line for m in mentions if m.context_line))
            cats, score, layer = classify_repo(first.full_name, context)

            # Boost score for repeat mentions
            score = min(100, score + (len(mentions) - 1) * 5)

            rec = RepoRecord(
                full_name=first.full_name,
                owner=first.owner,
                repo=first.repo,
                url=first.url,
                mentions_count=len(mentions),
                categories=cats,
                ultron_score=score,
                ultron_layer=layer,
                featured_in=[{
                    "video_id": m.video_id,
                    "video_title": m.video_title,
                    "timestamp": m.timestamp,
                    "context": m.context_line
                } for m in mentions],
                sample_context=context[:200]
            )
            records.append(rec)

        # Sort best first: ultron_score descending, then mentions_count descending
        records.sort(key=lambda r: (-r.ultron_score, -r.mentions_count, r.full_name.lower()))
        print(f"[Miner] Identified {len(records)} unique repositories after deduplication.")
        return records

    def export_catalog(self, records: List[RepoRecord], json_path: Path = DEFAULT_OUTPUT_JSON,
                       catalog_md: Path = DEFAULT_CATALOG_MD,
                       candidates_md: Path = DEFAULT_CANDIDATES_MD) -> None:
        """Export dataset as structured JSON and Markdown catalog."""
        # 1. JSON
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_data = [asdict(r) for r in records]
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[Miner] Saved JSON catalog to {json_path}")

        # 2. Complete Catalog Markdown
        catalog_md.parent.mkdir(parents=True, exist_ok=True)
        md_lines = [
            "# GitHub Awesome — Extracted Repository Catalog",
            "",
            f"Extracted from [@GithubAwesome](https://www.youtube.com/@GithubAwesome).",
            f"Total Unique Repositories: **{len(records)}**",
            "",
            "| Repository | Categories | Ultron Score | Mentions | Context / Note |",
            "|---|---|---|---|---|",
        ]
        for r in records:
            cats = ", ".join(r.categories)
            ctx = r.sample_context.replace("|", "/")
            md_lines.append(f"| [`{r.full_name}`]({r.url}) | {cats} | **{r.ultron_score}** | {r.mentions_count} | {ctx} |")

        catalog_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        print(f"[Miner] Saved complete markdown catalog to {catalog_md}")

        # 3. Top Ultron Native Integration Candidates
        candidates_md.parent.mkdir(parents=True, exist_ok=True)
        top_candidates = [r for r in records if r.ultron_score >= 65]

        top_lines = [
            "# Top GitHub Awesome Repositories for Native Ultron Integration",
            "",
            "Filtered by architectural synergy with Ultron's 6 layers (Voice, Vision, Agents, Memory, CLI, OS Control).",
            f"Selected Candidates: **{len(top_candidates)}** high-impact repositories.",
            "",
            "## Architectural Prioritization Matrix",
            "",
            "| Repository | Ultron Layer | Score | Key Capability & Integration Rationale |",
            "|---|---|---|---|",
        ]
        for r in top_candidates[:50]:
            top_lines.append(
                f"| [`{r.full_name}`]({r.url}) | {r.ultron_layer} | **{r.ultron_score}** | {r.sample_context or r.full_name} |"
            )

        candidates_md.write_text("\n".join(top_lines) + "\n", encoding="utf-8")
        print(f"[Miner] Saved Ultron integration candidates to {candidates_md}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine GitHub repositories from @GithubAwesome YouTube channel")
    parser.add_argument("--channel", default="https://www.youtube.com/@GithubAwesome/videos",
                        help="Channel or playlist URL")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max videos to inspect (default: all)")
    parser.add_argument("--workers", type=int, default=8,
                        help="Parallel workers for description extraction")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()

    miner = GithubAwesomeMiner()
    videos = miner.fetch_channel_videos(args.channel, limit=args.limit)
    videos = miner.populate_descriptions(videos, max_workers=args.workers)
    records = miner.mine_repositories(videos)
    miner.export_catalog(records, json_path=args.output_json)


if __name__ == "__main__":
    main()
