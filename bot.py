import os
import re
import requests
from typing import Optional, Dict, Any

from bs4 import BeautifulSoup
from dotenv import load_dotenv

import discord
from discord import app_commands
from yt_dlp import YoutubeDL

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

if not DISCORD_BOT_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN が未設定です (.env を確認)")

YOUTUBE_URL_RE = re.compile(
    r"(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+)"
)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def fetch_youtube_meta(url: str) -> Dict[str, str]:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        # うるさい警告を抑える（必要なら外してOK）
        "no_warnings": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "title": info.get("title") or "",
        "uploader": info.get("uploader") or info.get("channel") or "",
    }


def search_pitch_article(song_title: str, uploader: str) -> Optional[Dict[str, str]]:
    if not SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY が未設定です (.env を確認)")

    q = f"{song_title} {uploader} 最高音 最低音 平均音 音域"
    params = {
        "engine": "google",
        "q": q,
        "hl": "ja",
        "gl": "jp",
        "api_key": SERPAPI_KEY,
        "num": 5,
    }
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=20)
    r.raise_for_status()
    data: Dict[str, Any] = r.json()

    results = data.get("organic_results", [])
    if not results:
        return None

    top = results[0]
    return {
        "title": top.get("title", ""),
        "link": top.get("link", ""),
        "snippet": top.get("snippet", ""),
        "query": q,
    }


def extract_pitch_numbers(page_url: str) -> Dict[str, Optional[str]]:
    r = requests.get(page_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    def pick(label: str) -> Optional[str]:
        m = re.search(rf"{label}\s+([^\s（(]+)", text)
        return m.group(1) if m else None

    return {
        "highest": pick("最高音"),
        "lowest": pick("最低音"),
        "average": pick("平均値"),
    }


@tree.command(name="pitch", description="YouTube楽曲の音域（最高音/最低音/平均音）を調べます")
@app_commands.describe(url="YouTube の URL")
async def pitch(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True)

    m = YOUTUBE_URL_RE.search(url)
    if not m:
        await interaction.followup.send("❌ 正しい YouTube URL を入力してください")
        return

    try:
        meta = fetch_youtube_meta(m.group(1))
        song_title = meta["title"]
        uploader = meta["uploader"]

        if not song_title:
            await interaction.followup.send("❌ 曲名を取得できませんでした")
            return

        hit = search_pitch_article(song_title, uploader)
        if not hit:
            await interaction.followup.send("❌ 記事が見つかりませんでした")
            return

        p = extract_pitch_numbers(hit["link"])

        msg = [
            f"🎵 **{song_title}**",
            f"👤 {uploader or '不明'}",
            "",
            f"🔍 検索クエリ: {hit['query']}",
            f"📄 記事: {hit['title']}",
            f"🔗 {hit['link']}",
            "",
            "🎼 **音域**",
            f"・最高音: {p.get('highest') or '未取得'}",
            f"・最低音: {p.get('lowest') or '未取得'}",
            f"・平均音: {p.get('average') or '未取得'}",
        ]
        await interaction.followup.send("\n".join(msg))

    except Exception as e:
        await interaction.followup.send(f"❌ エラー: {type(e).__name__}: {e}")


@client.event
async def on_ready():
    # Guild同期（即反映）
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        synced = await tree.sync(guild=guild)
        print(f"Synced to guild({GUILD_ID}): {[c.name for c in synced]}")
    else:
        synced = await tree.sync()
        print(f"Synced globally: {[c.name for c in synced]}")

    print(f"Logged in as {client.user} (id={client.user.id})")


client.run(DISCORD_BOT_TOKEN)
