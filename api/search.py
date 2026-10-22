from api.client import get_json
from api.config import SEARCH_URL

def search_quizzes(query, limit=5):
    params = {"query": query, "cursor": 0, "limit": limit}
    data = get_json(SEARCH_URL, params=params)
    
    results = []
    for item in data.get("entities", []):
        quiz_data = item.get("kahoot", item.get("card", item))
        uuid = quiz_data.get("uuid")
        title = quiz_data.get("title", "Untitled")
        
        if uuid:
            results.append({"title": title, "uuid": uuid})
            
    return results
