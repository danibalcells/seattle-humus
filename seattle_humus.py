import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
import random
from dotenv import load_dotenv
from pylitterbot import Account
from openai import OpenAI


PALOMA_WEIGHT_THRESHOLD = 13.0
MIN_WEIGHT_FOR_NOTIFICATION = 10.0


MARGARITA_STICKER_IDS = [
    'CAACAgEAAxkBAAEPMytoppUVe7fyBDxR3Q50bQ9Eqa3qjAACGgQAAuewcEcNR614LPY-NDYE',
    'CAACAgEAAxkBAAEPMwtoppI9Dd2PtoDvB0kqJIsfshVmSwACvwQAAmK2aEcITvOjKzSM4DYE',
    'CAACAgEAAxkBAAEPMxFoppJhptR6-uJuKWdwz-z0nXoUmwACiAYAAgHpcUe-LriOk3onbzYE',
    'CAACAgEAAxkBAAEPMxVoppJ-zCaFifpQgEDp8XvYJ2LKSgACzAcAAixjuUSJbzbpmBy86DYE',
    'CAACAgEAAxkBAAEPMw1oppJLp6m7cfX6tXhhXUF7CQca_AACkQQAAuOnKEXKH-BDT3PXbTYE',
    'CAACAgEAAxkBAAEPMw9oppJVjZFoRHOkuqU4b0dnuYqaaAACrQUAAkCSKEVsRh8UNnqRYTYE'
]

PALOMA_STICKER_IDS = [
    'CAACAgEAAxkBAAEPMx1oppS6UNrkk-ac5A5OWjRL5BTVkgACtwYAAsnz-EYGt7LEVkwdczYE',
    'CAACAgEAAxkBAAEPMx9oppTLd9jKNieDINz1XyM0IfqcGQACQQUAAhBlGEfJFDs-5ppZqzYE',
    'CAACAgEAAxkBAAEPMyFoppTYcTlCi_P3gONJ5Zp1vd4GFQACnAQAAh1ycEe4rvsvvaNvAjYE',
    'CAACAgEAAxkBAAEPMyNoppTmBwdf3F3bGTZTPlBQSXy7egACEQYAAkGhWUSlEo0uccVLljYE',
    'CAACAgEAAxkBAAEPMxdoppKNBgKaoyVFHREOsl7Ec02IvQACPAYAAriqaETWOr6ybnBmdjYE',
    'CAACAgEAAxkBAAEPMxNoppJscrfOxiLybMYG8u2dYtLAUAACSQgAAu7QgEQoNA5yZ6AuDDYE',
    'CAACAgEAAxkBAAEPMyloppUCNs0Lo6MLj5Ves4JQUEo34gACZAUAApA4KEU185JASpuqGTYE',
    'CAACAgEAAxkBAAEPMzdoppVmKZesa4rL7k5J24PxBHEnRAACggUAAoRKKUU9gRbxNN_kXzYE',
    'CAACAgEAAxkBAAEPMzloppV2XV2wXxd1t-B3SH4PAZ9LkAACkwcAAtfFMUXGURcgacZdgDYE',
    'CAACAgEAAxkBAAEPMztoppWCWQKjOvDs7TmhsPEo-CIumwAC7gUAAkPxMUUvOQl8zn8XsjYE'
]

def parse_pet_weight(text: str) -> float:
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(?:lb|lbs)\b", text, re.IGNORECASE)
    if not match:
        raise ValueError("No weight found in text")
    return float(match.group(1))


def detect_cat(weight_lbs: float) -> str:
    return "Margarita" if weight_lbs < PALOMA_WEIGHT_THRESHOLD else "Paloma"


def format_timestamp(dt: datetime) -> str:
    local_dt = dt.astimezone()
    return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")


async def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, data=data)
        if resp.status_code != 200:
            raise RuntimeError(f"Telegram API error {resp.status_code}: {resp.text}")


async def send_telegram_sticker(token: str, chat_id: str, sticker_file_id: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendSticker"
    data = {"chat_id": chat_id, "sticker": sticker_file_id}
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, data=data)
        if resp.status_code != 200:
            if resp.status_code == 400 and "wrong file identifier" in resp.text.lower():
                return
            raise RuntimeError(f"Telegram API error {resp.status_code}: {resp.text}")


def choose_sticker_id(cat_name: str) -> str:
    if cat_name == "Margarita":
        return random.choice(MARGARITA_STICKER_IDS)
    return random.choice(PALOMA_STICKER_IDS)


def extract_weight_events(history: Iterable[Any]) -> List[Tuple[datetime, str]]:
    events: List[Tuple[datetime, str]] = []
    for event in history:
        action = getattr(event, "action", None)
        ts = getattr(event, "timestamp", None)
        if isinstance(action, str) and isinstance(ts, datetime) and action.lower().startswith("pet weight recorded"):
            events.append((ts, action))
    events.sort(key=lambda e: e[0])
    return events


def most_recent_timestamp(events: List[Tuple[datetime, str]]) -> Optional[datetime]:
    return events[-1][0] if events else None


def _require_openai_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY")


def generate_bathroom_message(cat_name: str, weight_lbs: float) -> str:
    _require_openai_key()
    client = OpenAI()
    prompt = (
        f"Cat name: {cat_name}\n"
        f"Weight: {weight_lbs:.2f} lbs\n"
        "Write a short sentence that is dorky and a bit unhinged about our cats lol "
        f"telling us that {cat_name} just used the bathroom, including their weight. Avoid emojis and hashtags"
        "Feel free to use nicknames for the cat like 'palouma', 'dovey', 'seattle' or whatever you want for Paloma, and 'margie', 'margaroo', 'margo', 'daisy' or 'hummus' for Margarita"
        "honestly tho feel free to say goofy shit like messing up grammar or misusing words"
        "For example: "
        "  - Hahahaha paloma just used the bathroom and weighs 10lbs"
        "  - Yo, heads up - margie went to the toilet. turns out she weighs 13lbs"
        "  - paloma weighs 12.9 pounds! that would be a lot of poop so thank god most of her is cuteness instead"
        "  - baby don't use the toilet in the living room for a while, margarita just made a mess. the LBS number is 13.1"
        "  - paloma just toileted the use and pounded 12.9"
        "  - mAAARG hehe you stanky little girl you should be 10 lbs proud"
        "  - the daisycat skibbed the di for 12.1 numbers of pound"
        "  - WHAT IF i told you that you could be a 10lb cat and still have a big poop. well that's what happened to margarita"
        "  - POUND POUND POUND POUND POUND POUND POUND POUND POUND POUND PO. That's 10.4 pounds just like margies latest weighing in at the tualet"
    )
    resp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": "You are a dorky cat lady spirit, all meaning is optional and must be found in the litter airport."},
            {"role": "user", "content": prompt},
        ],
        temperature=1.0,
        max_tokens=50,
    )
    content = resp.choices[0].message.content
    text = content if isinstance(content, str) and content else f"{cat_name} just used the bathroom and weighs {weight_lbs:.2f} lbs."
    return text.strip()


async def poll_litter_robot_and_notify(interval_seconds: int) -> None:
    load_dotenv()
    username = os.getenv("LITTERROBOT_USERNAME")
    password = os.getenv("LITTERROBOT_PASSWORD")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not username or not password:
        raise RuntimeError("Missing LITTERROBOT_USERNAME or LITTERROBOT_PASSWORD")
    if not tg_token or not tg_chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    account = Account()
    await account.connect(username=username, password=password, load_robots=True)
    try:
        last_seen_per_robot: Dict[str, Optional[datetime]] = {}
        for robot in account.robots:
            history = await getattr(robot, "get_activity_history")()
            weight_events = extract_weight_events(history)
            last_seen_per_robot[str(getattr(robot, "id", id(robot)))] = most_recent_timestamp(weight_events)

        while True:
            for robot in account.robots:
                robot_id = str(getattr(robot, "id", id(robot)))
                robot_name = getattr(robot, "name", str(robot))
                history = await getattr(robot, "get_activity_history")()
                weight_events = extract_weight_events(history)
                last_seen = last_seen_per_robot.get(robot_id)
                new_events: List[Tuple[datetime, str]] = []
                for ts, text in weight_events:
                    if last_seen is None or ts > last_seen:
                        new_events.append((ts, text))
                if new_events:
                    for ts, text in new_events:
                        weight = parse_pet_weight(text)
                        if weight > MIN_WEIGHT_FOR_NOTIFICATION:
                            cat = detect_cat(weight)
                            sticker_id = choose_sticker_id(cat)
                            await send_telegram_sticker(tg_token, tg_chat_id, sticker_id)
                            msg = await asyncio.to_thread(generate_bathroom_message, cat, weight)
                            await send_telegram_message(tg_token, tg_chat_id, msg)
                    last_seen_per_robot[robot_id] = new_events[-1][0]
            await asyncio.sleep(interval_seconds)
    finally:
        await account.disconnect()


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


async def _amain() -> None:
    interval = env_int("POLL_INTERVAL_SECONDS", 60)
    await poll_litter_robot_and_notify(interval)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()


