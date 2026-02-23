"""Quiz logic — reads content from DB, provides formatting and computation."""

# Display mapping: internal A/B/C -> user-facing А/Б/В
LETTER_DISPLAY = {"A": "А", "B": "Б", "C": "В"}

AGE_GROUPS = ["до 25", "26-35", "36-47", "старше 48"]


def compute_result(score_a: int, score_b: int, score_c: int) -> str:
    """Return winning letter with priority C > B > A on ties."""
    scores = {"A": score_a, "B": score_b, "C": score_c}
    priority = ["C", "B", "A"]
    max_score = max(scores.values())
    for letter in priority:
        if scores[letter] == max_score:
            return letter
    return "C"


def format_question(q: dict, index: int) -> str:
    """Format a question dict (from DB) into HTML message text."""
    lines = [
        f"<b>{q['title']}</b>",
        "",
        q["text"],
        "",
    ]
    for letter_key, field in [("A", "answer_a"), ("B", "answer_b"), ("C", "answer_c")]:
        display = LETTER_DISPLAY[letter_key]
        lines.append(f"<b>{display})</b> {q[field]}")
        lines.append("")
    return "\n".join(lines)


def format_result_message(result_text: dict, score_a: int, score_b: int, score_c: int) -> str:
    """Format a result_texts row (from DB) into HTML message."""
    r = result_text
    lines = [
        "📊 <b>Ваш результат</b>",
        "",
        f"А: {score_a}  |  Б: {score_b}  |  В: {score_c}",
        "",
        f"🏷 <b>Ваш стиль: {r['style']}</b> ({r['subtitle']})",
        "",
        r["description"],
        "",
        "⚠️ <b>Риски с поколением Z:</b>",
        r["risks"],
        "",
        "💡 <b>Совет:</b>",
        r["advice"],
    ]
    return "\n".join(lines)
