from datetime import date
import requests

def get_current_date():
    """
    Returns the current date in ISO format (YYYY-MM-DD)."""
    return date.today().isoformat()

def fetch_url_content(url):
    """
    Fetches the content of the given URL and returns it as text.
    """
    response = requests.get(url)
    response.raise_for_status()
    return response.text

# def google_web_search(query, api_key, cse_id, num_results=5):
#     """
#     Performs a Google web search using the Custom Search JSON API.
#     Returns a list of search result titles and links.

#     Args:
#         query (str): The search query.
#         api_key (str): Google API key.
#         cse_id (str): Custom Search Engine ID.
#         num_results (int): Number of results to return.

#     Returns:
#         list of dict: Each dict contains 'title' and 'link'.
#     """
#     url = "https://www.googleapis.com/customsearch/v1"
#     params = {
#         "q": query,
#         "key": api_key,
#         "cx": cse_id,
#         "num": num_results,
#     }
#     response = requests.get(url, params=params)
#     response.raise_for_status()
#     results = response.json().get("items", [])
#     return [{"title": item["title"], "link": item["link"]} for item in results]