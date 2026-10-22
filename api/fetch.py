import logging

from api.client import KahootAPIError, get_json
from api.config import QUIZ_URL

logger = logging.getLogger(__name__)


def get_quiz_answers(uuid):
    data = get_json(f"{QUIZ_URL}{uuid}")
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise KahootAPIError("Unexpected quiz data format: expected a list of questions.")

    questions_data = []
    for index, question in enumerate(data["questions"], start=1):
        warnings = []
        answers = []
        text = "Question text unavailable"
        if not isinstance(question, dict):
            warnings.append("Invalid question data. Answers could not be read.")
        else:
            raw_text = question.get("question")
            if isinstance(raw_text, str) and raw_text.strip():
                text = raw_text
            else:
                warnings.append("Question text is missing or has an unsupported format.")

            choices = question.get("choices")
            if not isinstance(choices, list):
                warnings.append("Answer choices are unavailable or have an unsupported format.")
            else:
                invalid_choices = False
                for choice in choices:
                    if not isinstance(choice, dict) or type(choice.get("correct")) is not bool:
                        invalid_choices = True
                        continue
                    if choice["correct"]:
                        answer = choice.get("answer")
                        if isinstance(answer, str) and answer.strip():
                            answers.append(answer)
                        else:
                            invalid_choices = True
                if invalid_choices:
                    answers = []
                    warnings.append("Some answer data could not be read. Answers are not shown for this question.")

        item = {"question": text, "answers": answers}
        if warnings:
            item["warning"] = " ".join(warnings)
            logger.warning("Question %s: %s", index, item["warning"])
        questions_data.append(item)
    return questions_data
