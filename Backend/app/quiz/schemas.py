from typing import List

from pydantic import BaseModel, Field, model_validator


class Question(BaseModel):
    id: str
    text: str = Field(min_length=1)
    choices: List[str] = Field(min_length=2, max_length=4)
    correct: int = Field(ge=0, description="Index of the correct choice")
    explanation: str = ""
    hint: str = Field("", description="Mnemonic / tip for remembering the answer")
    time_limit: int = Field(20, ge=5, le=120, description="Seconds")

    @model_validator(mode="after")
    def _check_choices(self) -> "Question":
        if self.correct >= len(self.choices):
            raise ValueError("correct index out of range")
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("duplicate choices")
        return self
