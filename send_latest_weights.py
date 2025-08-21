import asyncio
import os
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

from dotenv import load_dotenv
from pylitterbot import Account

from seattle_humus import (
    extract_weight_events,
    parse_pet_weight,
    send_telegram_message,
    generate_bathroom_message,
    choose_sticker_id,
    send_telegram_sticker,
)


def _latest_by_cat(events: Iterable[Tuple[datetime, str]]) -> Dict[str, Tuple[datetime, float]]:
    latest: Dict[str, Tuple[datetime, float]] = {}
    for ts, text in events:
        weight = parse_pet_weight(text)
        cat = "Margarita" if weight < 13.0 else "Paloma"
        prev = latest.get(cat)
        if prev is None or ts > prev[0]:
            latest[cat] = (ts, weight)
    return latest


async def _fetch_latest_weights() -> Dict[str, Tuple[datetime, float]]:
    load_dotenv()
    username = os.getenv("LITTERROBOT_USERNAME")
    password = os.getenv("LITTERROBOT_PASSWORD")
    if not username or not password:
        raise RuntimeError("Missing LITTERROBOT_USERNAME or LITTERROBOT_PASSWORD")
    account = Account()
    await account.connect(username=username, password=password, load_robots=True)
    try:
        all_events: List[Tuple[datetime, str]] = []
        for robot in account.robots:
            history = await getattr(robot, "get_activity_history")()
            all_events.extend(extract_weight_events(history))
        return _latest_by_cat(all_events)
    finally:
        await account.disconnect()


async def _amain() -> None:
    load_dotenv()
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not tg_token or not tg_chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    latest = await _fetch_latest_weights()
    ordered = ["Margarita", "Paloma"]
    for name in ordered:
        entry = latest.get(name)
        if not entry:
            continue
        _, weight = entry
        sticker_id = choose_sticker_id(name)
        await send_telegram_sticker(tg_token, tg_chat_id, sticker_id)
        msg = await asyncio.to_thread(generate_bathroom_message, name, weight)
        await send_telegram_message(tg_token, tg_chat_id, msg)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()


