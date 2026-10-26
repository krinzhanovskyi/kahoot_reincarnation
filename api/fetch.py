import logging

from api.client import KahootAPIError, get_json
from api.config import QUIZ_URL
from api.text import clean_text, contains_image

logger = logging.getLogger(__name__)

CHOICE_TYPES = {"quiz", "true_false"}
OPINION_TYPES = {"survey", "poll", "word_cloud", "brainstorm", "scale", "nps"}
CONTENT_TYPES = {"content", "slide"}
UNSUPPORTED_MESSAGES = {
    "jumble": "Puzzle requires an ordered answer. This format is not supported yet.",
    "puzzle": "Puzzle requires an ordered answer. This format is not supported yet.",
    "open_ended": "This open-ended format is not supported yet; accepted answers are not inferred.",
    "type_answer": "Typed-answer extraction is not supported yet.",
    "slider": "Numeric answers and their tolerance are not supported yet.",
    "pin_it": "Image-coordinate answers are not supported yet.",
}


def _read_choices(choices):
    if not isinstance(choices, list):
        return [], "invalid_data", "Answer choices are unavailable or have an unsupported format."
    answers = []
    invalid = False
    media_answer = False
    for choice in choices:
        if not isinstance(choice, dict) or type(choice.get("correct")) is not bool:
            invalid = True
            continue
        if not choice["correct"]:
            continue
        answer = clean_text(choice.get("answer"))
        if contains_image(choice.get("answer")):
            media_answer = True
        elif isinstance(answer, str) and answer.strip():
            answers.append(answer)
        elif choice.get("image") or choice.get("media"):
            media_answer = True
        else:
            invalid = True
    if invalid:
        return [], "invalid_data", "Some answer data could not be read. Answers are not shown for this question."
    if media_answer:
        return [], "unsupported", "A correct answer uses media without text. Media answers are not supported yet."
    if not answers:
        return [], "no_correct_answer", "The data does not mark any correct text answer."
    return answers, "supported", ""


def parse_question(question):
    item = {"question": "Question text unavailable", "answers": [],
            "type": "unknown", "status": "invalid_data"}
    if not isinstance(question, dict):
        item["warning"] = "Invalid question data. Answers could not be read."
        return item

    raw_type = question.get("type", "unspecified")
    valid_type = isinstance(raw_type, str) and bool(raw_type.strip())
    if valid_type:
        item["type"] = raw_type.strip().lower()
    kind = item["type"]
    warnings = []
    text = clean_text(question.get("question"))
    if kind in CONTENT_TYPES and (not isinstance(text, str) or not text.strip()):
        text = clean_text(question.get("title", "Slide"))
    if isinstance(text, str) and text.strip():
        item["question"] = text
    elif kind in CONTENT_TYPES:
        item["question"] = "Slide"
    else:
        warnings.append("Question text is missing or has an unsupported format.")

    if not valid_type:
        warnings.append("Question type is invalid. Answers were not extracted.")
    elif kind in CONTENT_TYPES:
        item["status"] = "content"
        item["message"] = "This is a content slide; no answer is required."
    elif kind in OPINION_TYPES:
        item["status"] = "no_answer_required"
        item["message"] = "This item collects opinions; there is no correct answer."
    elif kind in CHOICE_TYPES or kind == "unspecified":
        answers, status, message = _read_choices(question.get("choices"))
        item["answers"] = answers
        item["status"] = status
        if status == "invalid_data":
            warnings.append(message)
        elif message:
            item["message"] = message
        if kind == "unspecified" and status == "supported":
            item["message"] = "Type not provided; answers read from explicit correct flags."
    else:
        item["status"] = "unsupported"
        item["message"] = UNSUPPORTED_MESSAGES.get(
            kind, "This question type is not supported yet. Answers were not extracted."
        )

    if warnings:
        item["warning"] = " ".join(warnings)
    return item


def get_quiz_answers(uuid):
    data = get_json(f"{QUIZ_URL}{uuid}")
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise KahootAPIError("Unexpected quiz data format: expected a list of questions.")
    questions_data = []
    for index, question in enumerate(data["questions"], start=1):
        item = parse_question(question)
        if item.get("warning"):
            logger.warning("Question %s: %s", index, item["warning"])
        questions_data.append(item)
    return questions_data
