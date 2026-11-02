MAX_POINTS = 1000
STREAK_BONUS = 100
MAX_STREAK_BONUS = 500


def points_for_answer(correct: bool, elapsed: float, time_limit: float, streak: int) -> int:
    """Points for one answer.

    `elapsed` is measured by the server. `streak` is the number of correct answers
    in a row *before* this one, so the second correct answer in a row gets +100.
    """
    if not correct:
        return 0
    ratio = min(max(elapsed / time_limit, 0.0), 1.0)
    base = round(MAX_POINTS * (1 - 0.5 * ratio))
    bonus = min(streak * STREAK_BONUS, MAX_STREAK_BONUS)
    return base + bonus
