import re

import requests
from python_a2a import A2AServer, TaskState, TaskStatus, agent, run_server, skill

import config
from travel_utils import (
    configure_logging,
    extract_location,
    extract_message_text,
    text_artifact,
)

logger = configure_logging("search-agent")

ACTIVITY_KEYWORDS = [
    "recommend", "activities", "things to do", "attractions", "restaurants",
    "hotels", "places to visit", "outdoor", "indoor", "sightseeing",
    "museums", "entertainment", "nightlife", "shopping", "tours",
]

_HTML_TAG = re.compile(r"<[^>]+>")
_CITY_ALIASES = {
    "new york city": "new york",
    "nyc": "new york",
    "the big apple": "new york",
    "roma": "rome",
    "firenze": "florence",
    "tokyo japan": "tokyo",
}


@agent(
    name="Smart Search Agent",
    description="Provides location search, geocoding, and activity recommendations for travel planning",
    version="2.1.0",
    url=config.SEARCH_AGENT_URL,
)
class LocationSearchAgent(A2AServer):

    @skill(
        name="Search",
        description="Smart search that handles both location queries and activity recommendations",
        tags=["location", "coordinates", "geocoding", "activities", "recommendations", "brave"],
        examples="Search for 'New York City' or 'restaurants in Paris' or 'outdoor activities in London'",
    )
    def search(self, query: str):
        """Smart search that determines if it's a location or activity query"""
        if not query or not query.strip():
            return "Please provide a search query or location to find."

        is_activity_query = any(keyword in query.lower() for keyword in ACTIVITY_KEYWORDS)

        if is_activity_query:
            return self._handle_activity_recommendation(query)
        return self._handle_location_search(query)

    # --- Activity recommendations -------------------------------------------

    def _handle_activity_recommendation(self, query: str):
        """Handle activity and recommendation queries.

        Live results come from the Brave Search API when ``BRAVE_API_KEY`` is
        configured; otherwise the curated database is used.
        """
        query_lower = query.lower()
        location = self._extract_location_from_query(query)
        category = self._category_for(query_lower)

        if config.has_brave_api_key():
            live = self._brave_activity_results(location, category)
            if live:
                return (
                    f"Activity recommendations for {location} "
                    f"(live Brave Search results):\n\n{live}"
                )
            logger.info("brave search returned nothing, using curated recommendations")

        activities = self._curated_activities(category, location)
        return f"Activity recommendations for {location}:\n\n{activities}"

    @staticmethod
    def _category_for(query_lower: str):
        """Map a free-form query onto a recommendation category."""
        if "outdoor" in query_lower:
            return "outdoor"
        if "indoor" in query_lower:
            return "indoor"
        if "restaurant" in query_lower or "food" in query_lower:
            return "restaurant"
        if "museum" in query_lower:
            return "museum"
        return "general"

    def _curated_activities(self, category, location):
        """Curated recommendations for a category, with a generic fallback."""
        if category == "outdoor":
            return self._get_outdoor_activities(location)
        if category == "indoor":
            return self._get_indoor_activities(location)
        if category == "restaurant":
            return self._get_restaurant_recommendations(location)
        if category == "museum":
            return self._get_museum_recommendations(location)
        return self._get_general_activities(location)

    def _extract_location_from_query(self, query: str):
        """Extract location from activity query"""
        return extract_location(query, default="the location")

    @staticmethod
    def _location_key(location):
        """Normalise a location into a curated-database key."""
        key = re.sub(r"^the\s+", "", (location or "").strip().lower())
        key = re.sub(r"\s+", " ", key).strip(" ,.")
        return _CITY_ALIASES.get(key, key)

    def _get_outdoor_activities(self, location):
        """Get outdoor activity recommendations"""
        activities = {
            "paris": [
                "Seine River cruise and walk along the riverbank",
                "Picnic in Luxembourg Gardens or Tuileries Garden",
                "Climb the Eiffel Tower for panoramic city views",
                "Explore Montmartre district and Sacré-Cœur Basilica",
                "Bike tour through the Marais district",
                "Walking tour of the Latin Quarter",
            ],
            "london": [
                "Hyde Park and Speaker's Corner visit",
                "Thames River walking path and Tower Bridge",
                "Camden Market and Regent's Canal walk",
                "Greenwich Park and Royal Observatory",
                "Hampstead Heath for city views",
                "Covent Garden street performances",
            ],
            "tokyo": [
                "Cherry blossom viewing in Ueno Park",
                "Senso-ji Temple in Asakusa district",
                "Shibuya Crossing experience",
                "Harajuku and Takeshita Street exploration",
                "Imperial Palace East Gardens",
                "Odaiba Beach and Rainbow Bridge",
            ],
            "new york": [
                "Central Park loop and Bethesda Terrace",
                "High Line elevated park walk to Chelsea Market",
                "Brooklyn Bridge crossing at sunset",
                "Staten Island Ferry for Statue of Liberty views",
                "Governors Island bike ride",
                "Coney Island boardwalk and beach",
            ],
            "rome": [
                "Colosseum and Roman Forum walking route",
                "Villa Borghese gardens and terrace views",
                "Trastevere evening stroll",
                "Appian Way bike ride past ancient tombs",
                "Piazza Navona and Trevi Fountain circuit",
                "Janiculum Hill panorama at sunset",
            ],
            "barcelona": [
                "Park Güell and its mosaic terraces",
                "Barceloneta beach and seafront promenade",
                "Montjuïc cable car and castle viewpoint",
                "Gothic Quarter walking tour",
                "Bunkers del Carmel for skyline views",
                "Day hike up Tibidabo",
            ],
            "amsterdam": [
                "Canal belt cycling route",
                "Vondelpark picnic",
                "Boat tour through the Jordaan",
                "Keukenhof or Bloemenmarkt flower stops",
                "NDSM wharf ferry and street art",
                "Amsterdamse Bos for a longer walk",
            ],
            "sydney": [
                "Bondi to Coogee coastal walk",
                "Sydney Harbour Bridge climb or walkway",
                "Royal Botanic Garden and Mrs Macquarie's Chair",
                "Manly Beach ferry trip",
                "Taronga Zoo harbour views",
                "Kayaking around Lane Cove National Park",
            ],
            "dubai": [
                "Dubai Marina waterfront walk (early morning)",
                "Desert safari with dune driving",
                "Kite Beach and Burj Al Arab views",
                "Dubai Creek abra ride to the souks",
                "Al Fahidi historical district stroll",
                "Palm Jumeirah boardwalk",
            ],
            "singapore": [
                "Gardens by the Bay and Supertree Grove",
                "Marina Bay waterfront promenade",
                "Southern Ridges canopy walk",
                "Sentosa beaches and cable car",
                "Singapore Botanic Gardens orchid trail",
                "Kampong Glam and Haji Lane exploration",
            ],
        }
        return self._render(activities, location, [
            "Explore local parks and outdoor markets",
            "Walking tours of historic districts",
            "Riverfront or waterfront areas",
            "Local hiking trails or scenic viewpoints",
            "Outdoor cafés and street food areas",
            "Public gardens and green spaces",
        ])

    def _get_indoor_activities(self, location):
        """Get indoor activity recommendations"""
        activities = {
            "paris": [
                "Louvre Museum - see the Mona Lisa and Venus de Milo",
                "Musée d'Orsay for Impressionist masterpieces",
                "Palace of Versailles (day trip from Paris)",
                "Sainte-Chapelle for stunning stained glass",
                "Shopping at Galeries Lafayette and Printemps",
                "Les Invalides and Napoleon's Tomb",
            ],
            "london": [
                "British Museum and Rosetta Stone",
                "Tate Modern art gallery",
                "Westminster Abbey and Houses of Parliament tour",
                "Shopping in Oxford Street and Covent Garden",
                "National Gallery in Trafalgar Square",
                "Borough Market for food tasting",
            ],
            "tokyo": [
                "Tokyo National Museum in Ueno",
                "Meiji Shrine indoor areas",
                "Tsukiji Outer Market food halls",
                "Department stores in Ginza (Mitsukoshi, Ginza Six)",
                "Akihabara electronics and anime culture",
                "Traditional tea ceremony experience",
            ],
            "new york": [
                "Metropolitan Museum of Art",
                "American Museum of Natural History",
                "MoMA and its film programme",
                "Grand Central Terminal and Chelsea Market",
                "Broadway matinee performance",
                "Top of the Rock observation deck",
            ],
            "rome": [
                "Vatican Museums and the Sistine Chapel",
                "Galleria Borghese (book ahead)",
                "Pantheon interior",
                "Capitoline Museums",
                "Castel Sant'Angelo",
                "Roman cooking or pasta-making class",
            ],
            "barcelona": [
                "Sagrada Família interior",
                "Casa Batlló and La Pedrera",
                "Picasso Museum in El Born",
                "Mercat de la Boqueria food stalls",
                "Palau de la Música Catalana tour",
                "MNAC on Montjuïc",
            ],
            "amsterdam": [
                "Rijksmuseum",
                "Van Gogh Museum",
                "Anne Frank House (timed tickets)",
                "Foodhallen indoor food market",
                "Royal Palace on Dam Square",
                "Concertgebouw concert",
            ],
            "sydney": [
                "Sydney Opera House interior tour",
                "Art Gallery of New South Wales",
                "Australian Museum",
                "Queen Victoria Building shopping",
                "SEA LIFE Sydney Aquarium",
                "The Rocks Discovery Museum",
            ],
            "dubai": [
                "Dubai Mall and the Dubai Aquarium",
                "Burj Khalifa At the Top observation deck",
                "Museum of the Future",
                "Dubai Frame",
                "Gold and Spice souks (covered lanes)",
                "Etihad Museum",
            ],
            "singapore": [
                "National Museum of Singapore",
                "ArtScience Museum at Marina Bay Sands",
                "Cloud Forest dome",
                "Hawker centres such as Maxwell Food Centre",
                "Peranakan Museum",
                "Jewel Changi indoor waterfall",
            ],
        }
        return self._render(activities, location, [
            "Local museums and art galleries",
            "Historic buildings and monuments",
            "Shopping centers and markets",
            "Cultural centers and theaters",
            "Traditional craft workshops",
            "Local cuisine cooking classes",
        ])

    def _render(self, database, location, fallback):
        """Render curated entries for a location, else the generic fallback."""
        entries = database.get(self._location_key(location), fallback)
        return "\n".join(f"• {entry}" for entry in entries)

    def _get_restaurant_recommendations(self, location):
        """Get restaurant recommendations"""
        return self._render({}, location, [
            "Local traditional cuisine restaurants",
            "Highly-rated cafés and bistros",
            "Food markets with local specialties",
            "Rooftop restaurants with city views",
            "Historic restaurants with cultural significance",
            "Street food vendors and food halls",
        ])

    def _get_museum_recommendations(self, location):
        """Get museum recommendations"""
        return self._render({}, location, [
            "National and history museums",
            "Art galleries featuring local artists",
            "Science and technology museums",
            "Cultural heritage centers",
            "Archaeological museums",
            "Contemporary art spaces",
        ])

    def _get_general_activities(self, location):
        """Get general activity recommendations"""
        return self._render({}, location, [
            "Top historical landmarks and monuments",
            "Local markets and shopping districts",
            "Traditional cultural experiences",
            "Popular viewpoints and photo spots",
            "Local food specialties and restaurants",
            "Walking tours of historic neighborhoods",
        ])

    # --- Brave Search --------------------------------------------------------

    def _brave_activity_results(self, location, category):
        """Formatted live results for a location/category, or '' when unavailable."""
        phrases = {
            "outdoor": "best outdoor activities in",
            "indoor": "best indoor things to do in",
            "restaurant": "best restaurants in",
            "museum": "best museums in",
            "general": "top attractions in",
        }
        results = self.brave_search(f"{phrases.get(category, phrases['general'])} {location}")
        if not results:
            return ""

        lines = []
        for result in results:
            lines.append(f"• {result['title']}")
            if result["description"]:
                lines.append(f"  {result['description']}")
            if result["url"]:
                lines.append(f"  {result['url']}")
        return "\n".join(lines)

    def brave_search(self, query, count=None):
        """Query the Brave Search API and return normalised web results."""
        if not config.has_brave_api_key():
            return []

        try:
            response = requests.get(
                config.BRAVE_SEARCH_URL,
                params={
                    "q": query,
                    "count": count or config.BRAVE_RESULT_COUNT,
                    "safesearch": "moderate",
                    "result_filter": "web",
                },
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": config.BRAVE_API_KEY,
                    "User-Agent": config.USER_AGENT,
                },
                timeout=config.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as e:
            # Never log the response body or the key itself.
            logger.warning("brave search request failed: %s", type(e).__name__)
            return []
        except ValueError:
            logger.warning("brave search returned a non-JSON response")
            return []

        return self._parse_brave_results(payload)

    @staticmethod
    def _parse_brave_results(payload):
        """Normalise a Brave Search payload into title/description/url dicts."""
        results = []
        for item in ((payload or {}).get("web") or {}).get("results") or []:
            title = _HTML_TAG.sub("", item.get("title") or "").strip()
            if not title:
                continue
            description = _HTML_TAG.sub("", item.get("description") or "").strip()
            results.append({
                "title": title,
                "description": description,
                "url": item.get("url", ""),
            })
        return results

    # --- Location search -----------------------------------------------------

    def _handle_location_search(self, query: str):
        """Handle pure location search using Nominatim API"""
        params = {
            "q": query,
            "format": "json",
            "limit": 5,
            "addressdetails": 1,
            "extratags": 1,
        }

        try:
            response = requests.get(
                config.NOMINATIM_URL,
                params=params,
                timeout=config.REQUEST_TIMEOUT,
                headers={"User-Agent": config.USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error("error during location search: %s", e)
            return f"Location search failed: {e}"
        except ValueError:
            return "Location search failed: the geocoding service returned invalid data."

        if not data:
            return f"No location results found for '{query}'."

        results = []
        for result in data:
            display_name = result.get("display_name", "Unknown location")
            lat = result.get("lat", "N/A")
            lon = result.get("lon", "N/A")
            place_type = result.get("type", "location")
            importance = result.get("importance", 0) or 0

            results.append(f"- {display_name}")
            results.append(f"  Type: {place_type}")
            results.append(f"  Coordinates: {lat}, {lon}")
            results.append(f"  Importance: {float(importance):.3f}")
            results.append("")

        return f"Location search results for '{query}':\n\n" + "\n".join(results)

    def handle_task(self, task):
        text = extract_message_text(task)

        if text:
            task.artifacts = text_artifact(self.search(text))
            task.status = TaskStatus(state=TaskState.COMPLETED)
        else:
            task.status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message={"role": "agent", "content": {"type": "text",
                         "text": "Please provide a search query or location to find."}},
            )
        return task


if __name__ == "__main__":
    search_agent = LocationSearchAgent(google_a2a_compatible=True)
    logger.info(
        "starting search agent on port %s (brave search %s)",
        config.SEARCH_AGENT_PORT,
        "enabled" if config.has_brave_api_key() else "disabled",
    )
    run_server(search_agent, host=config.AGENT_HOST, port=config.SEARCH_AGENT_PORT)
