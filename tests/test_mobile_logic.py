import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mobile"))

from taskstack_logic import (  # noqa: E402
    compute_stats,
    deadline_from_choice,
    filter_tasks,
    normalize_deadline_text,
    normalize_task,
    parse_deadline,
    priority_rank,
    sort_tasks,
)

NOW = datetime(2026, 11, 14, 12, 0)


def raw(task_id, title="t", status=0, deadline="", user_id=1, author="me", **extra):
    return {
        "id": task_id,
        "title": title,
        "status": status,
        "priority": extra.pop("priority", "⚡ Средний"),
        "category": extra.pop("category", "📌 Прочее"),
        "deadline": deadline,
        "user_id": user_id,
        "author_username": author,
        **extra,
    }


def norm(*args, **kwargs):
    return normalize_task(raw(*args, **kwargs), 1, "me", NOW)


class LogicTests(unittest.TestCase):
    def test_priority_rank_works_for_both_languages(self):
        self.assertEqual(priority_rank("🔥 Высокий"), 0)
        self.assertEqual(priority_rank("🔥 High"), 0)
        self.assertEqual(priority_rank("☕ Low"), 2)
        self.assertEqual(priority_rank("unknown"), 1)
        self.assertEqual(priority_rank(None), 1)

    def test_deadline_parsing(self):
        self.assertEqual(parse_deadline("2026-11-14 09:30"), datetime(2026, 11, 14, 9, 30))
        self.assertIsNone(parse_deadline(""))
        self.assertIsNone(parse_deadline("tomorrow"))

    def test_normalize_deadline_text(self):
        self.assertEqual(normalize_deadline_text(" 2026-11-14 09:30 "), "2026-11-14 09:30")
        self.assertEqual(normalize_deadline_text(""), "")
        self.assertIsNone(normalize_deadline_text("14.11.2026"))

    def test_quick_deadlines(self):
        self.assertEqual(deadline_from_choice("today", NOW), "2026-11-14 23:59")
        self.assertEqual(deadline_from_choice("tomorrow", NOW), "2026-11-15 23:59")
        self.assertEqual(deadline_from_choice("week", NOW), "2026-11-21 23:59")
        self.assertEqual(deadline_from_choice("none", NOW), "")

    def test_overdue_only_for_open_tasks(self):
        self.assertTrue(norm(1, deadline="2026-11-13 10:00")["overdue"])
        self.assertFalse(norm(2, deadline="2026-11-13 10:00", status=1)["overdue"])
        self.assertFalse(norm(3, deadline="2026-11-20 10:00")["overdue"])
        self.assertFalse(norm(4, deadline="garbage")["overdue"])

    def test_author_and_ownership(self):
        own = norm(1)
        self.assertTrue(own["isOwner"])
        self.assertEqual(own["author"], "")
        incoming = norm(2, user_id=5, author="anna")
        self.assertFalse(incoming["isOwner"])
        self.assertEqual(incoming["author"], "anna")
        outgoing = norm(3, shared_with_ids=[5])
        self.assertTrue(outgoing["shared"])
        self.assertEqual(outgoing["author"], "me")

    def test_sort_open_first_then_deadline_then_priority(self):
        tasks = [
            norm(1, status=1, deadline="2026-11-01 10:00"),
            norm(2),
            norm(3, deadline="2026-11-20 10:00"),
            norm(4, deadline="2026-11-16 10:00"),
            norm(5, priority="🔥 Высокий"),
        ]
        self.assertEqual([t["id"] for t in sort_tasks(tasks)], [4, 3, 5, 2, 1])

    def test_filtering(self):
        tasks = [
            norm(1, title="Buy Milk", category="🏠 Личное"),
            norm(2, title="Write report", status=1, category="📚 Учёба"),
            norm(3, title="Call mom", category="🏠 Личное"),
        ]
        self.assertEqual(len(filter_tasks(tasks)), 3)
        self.assertEqual([t["id"] for t in filter_tasks(tasks, "active")], [1, 3])
        self.assertEqual([t["id"] for t in filter_tasks(tasks, "completed")], [2])
        self.assertEqual([t["id"] for t in filter_tasks(tasks, search="MILK")], [1])
        self.assertEqual(
            [t["id"] for t in filter_tasks(tasks, category="🏠 Личное")], [1, 3]
        )
        self.assertEqual(
            [t["id"] for t in filter_tasks(tasks, "active", "call", "🏠 Личное")], [3]
        )

    def test_stats(self):
        self.assertEqual(
            compute_stats([]),
            {"total": 0, "done": 0, "active": 0, "overdue": 0, "percent": 0},
        )
        stats = compute_stats(
            [norm(1, status=1), norm(2, deadline="2026-11-01 10:00"), norm(3)]
        )
        self.assertEqual(
            stats, {"total": 3, "done": 1, "active": 2, "overdue": 1, "percent": 33}
        )


if __name__ == "__main__":
    unittest.main()
