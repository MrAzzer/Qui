from typing import List

from app.quiz.schemas import Question

SAMPLE_QUESTIONS: List[Question] = [
    Question(
        id="q1",
        text="Które organellum odpowiada za produkcję ATP?",
        choices=["Rybosom", "Mitochondrium", "Aparat Golgiego", "Lizosom"],
        correct=1,
        explanation="Mitochondria przeprowadzają oddychanie komórkowe, w którym powstaje ATP.",
        hint="MITOchondrium = MOTOR komórki — daje energię jak silnik.",
    ),
    Question(
        id="q2",
        text="Ile wynosi pochodna funkcji f(x) = x²?",
        choices=["x", "2x", "x²/2", "2"],
        correct=1,
        explanation="Z reguły potęgowej: (xⁿ)' = n·xⁿ⁻¹.",
        hint="Wykładnik „schodzi” przed x, a sam zmniejsza się o 1.",
    ),
    Question(
        id="q3",
        text="W którym roku rozpoczęła się II wojna światowa?",
        choices=["1914", "1939", "1945", "1918"],
        correct=1,
        explanation="1 września 1939 Niemcy zaatakowały Polskę.",
        hint="39 — „trzy dziewiątki wrzesień”: wojna wybuchła we wrześniu ’39.",
    ),
]


def get_sample_questions() -> List[Question]:
    return [q.model_copy() for q in SAMPLE_QUESTIONS]
