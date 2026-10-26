import logging

from api.client import KahootAPIError, get_json
from api.config import SEARCH_URL
from api.text import clean_text

logger = logging.getLogger(__name__)


def search_quizzes(query, limit=5):
    params = {"query": query, "cursor": 0, "limit": limit}
    data = get_json(SEARCH_URL, params=params)
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
        raise KahootAPIError("Unexpected search data format: expected a list of quizzes.")

    results = []
    for index, item in enumerate(data["entities"]):
        quiz_data = None
        if isinstance(item, dict):
            for candidate in (item.get("kahoot"), item.get("card"), item):
                if isinstance(candidate, dict):
                    uuid = candidate.get("uuid")
                    if isinstance(uuid, str) and uuid.strip():
                        quiz_data = candidate
                        break
        if quiz_data is None:
            logger.warning("Skipped search result %s: missing valid UUID", index + 1)
            continue
        title = clean_text(quiz_data.get("title"))
        if not isinstance(title, str) or not title.strip():
            title = "Untitled"
        results.append({"title": title, "uuid": quiz_data["uuid"].strip()})

    if data["entities"] and not results:
        raise KahootAPIError("Kahoot returned quizzes, but none had a valid identifier.")
    return results
