"""Punktacja: 500–1000 pkt za dobrą odpowiedź (szybciej = więcej) + seria do +500."""

MAX_POINTS = 1000
STREAK_BONUS = 100
MAX_STREAK_BONUS = 500


def points_for_answer(correct: bool, elapsed: float, time_limit: float, streak: int) -> int:
    """Punkty za jedną odpowiedź.

    `elapsed` mierzy serwer (nie telefon). `streak` to liczba dobrych odpowiedzi z rzędu *przed* tą,
    więc druga dobra odpowiedź z rzędu dostaje +100, szósta i kolejne +500.
    """
    if not correct:
        return 0
    ratio = min(max(elapsed / time_limit, 0.0), 1.0)
    base = round(MAX_POINTS * (1 - 0.5 * ratio))
    bonus = min(streak * STREAK_BONUS, MAX_STREAK_BONUS)
    return base + bonus
