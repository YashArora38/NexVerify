"""Best-effort minimization of user submissions, not a guarantee of anonymization."""
import re


def minimize_text(text: str) -> str:
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[email redacted]", text)
    text = re.sub(r"(?<!\w)(?:\d{4}[ -]?){2}\d{4}(?!\w)", "[12-digit identifier redacted]", text)
    text = re.sub(r"(?<!\w)(?:\+91[ -]?)?[6-9]\d{9}(?!\w)", "[phone redacted]", text)
    return text


def minimize_answers(answers: dict) -> dict:
    allowed = {"received_via", "asking_money_or_otp", "promises"}
    if set(answers) - allowed or any(not isinstance(v, str) or len(v) > 1000 for v in answers.values()):
        raise ValueError("Only the three bounded questionnaire answers are accepted")
    return {k: minimize_text(v) for k, v in answers.items()}
