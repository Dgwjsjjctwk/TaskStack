"""Presentation logic for the mobile client, free of any Qt dependency."""

from datetime import datetime, timedelta

DEADLINE_FORMAT = "%Y-%m-%d %H:%M"

PRIORITY_CHOICES = {
    "ru": ["⚡ Средний", "🔥 Высокий", "☕ Низкий"],
    "en": ["⚡ Medium", "🔥 High", "☕ Low"],
}
CATEGORY_CHOICES = {
    "ru": ["💻 Разработка", "📚 Учёба", "🏠 Личное", "📌 Прочее"],
    "en": ["💻 Development", "📚 Study", "🏠 Personal", "📌 Other"],
}

# Tasks are stored with whatever language the creating client used, so the
# priority level is recognised by its emoji, not by its text.
_PRIORITY_RANK = {"🔥": 0, "⚡": 1, "☕": 2}


def priority_rank(priority):
    for emoji, rank in _PRIORITY_RANK.items():
        if emoji in (priority or ""):
            return rank
    return 1


def parse_deadline(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, DEADLINE_FORMAT)
    except ValueError:
        return None


def deadline_from_choice(choice, now=None):
    """Turn a quick-pick token into a deadline string ('' means none)."""
    now = now or datetime.now()
    end_of_day = now.replace(hour=23, minute=59, second=0, microsecond=0)
    offsets = {"today": 0, "tomorrow": 1, "week": 7}
    if choice in offsets:
        return (end_of_day + timedelta(days=offsets[choice])).strftime(DEADLINE_FORMAT)
    return ""


def normalize_deadline_text(text):
    """Return a canonical deadline string, '' for empty, None if invalid."""
    text = (text or "").strip()
    if not text:
        return ""
    parsed = parse_deadline(text)
    return parsed.strftime(DEADLINE_FORMAT) if parsed else None


def normalize_task(raw, current_user_id, current_username, now=None):
    now = now or datetime.now()
    completed = bool(raw.get("status"))
    deadline = raw.get("deadline") or ""
    parsed = parse_deadline(deadline)
    author = raw.get("author_username") or ""
    is_owner = raw.get("user_id") == current_user_id
    shared_out = bool(raw.get("shared_with_ids") or raw.get("shared_with_group_ids"))
    return {
        "id": raw["id"],
        "title": raw.get("title", ""),
        "completed": completed,
        "priority": raw.get("priority", ""),
        "priorityRank": priority_rank(raw.get("priority")),
        "category": raw.get("category", ""),
        "deadline": deadline,
        "overdue": bool(parsed and not completed and parsed < now),
        "isOwner": is_owner,
        # Show an author only for tasks someone else shared with this user,
        # or that the user shared with others.
        "author": "" if author == current_username and not shared_out else author,
        "shared": shared_out,
    }


def sort_tasks(tasks):
    """Open tasks first, then by deadline (undated last), then priority."""

    def key(task):
        parsed = parse_deadline(task["deadline"])
        return (
            task["completed"],
            parsed is None,
            parsed or datetime.max,
            task["priorityRank"],
            task["id"],
        )

    return sorted(tasks, key=key)


def filter_tasks(tasks, status="all", search="", category=""):
    search = (search or "").strip().lower()
    result = []
    for task in tasks:
        if status == "active" and task["completed"]:
            continue
        if status == "completed" and not task["completed"]:
            continue
        if category and task["category"] != category:
            continue
        if search and search not in task["title"].lower():
            continue
        result.append(task)
    return result


def compute_stats(tasks):
    total = len(tasks)
    done = sum(1 for task in tasks if task["completed"])
    return {
        "total": total,
        "done": done,
        "active": total - done,
        "overdue": sum(1 for task in tasks if task["overdue"]),
        "percent": int(round(100 * done / total)) if total else 0,
    }
