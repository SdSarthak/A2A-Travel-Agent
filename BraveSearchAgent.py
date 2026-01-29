from python_a2a import A2AServer, skill, agent, run_server, TaskStatus, TaskState
import os
import requests
import logging
@agent(
    name="Smart Search Agent",
    description="Provides location search, geocoding, and activity recommendations for travel planning",
    version="2.0.0",
    url="https://yourdomain.com"
)
class LocationSearchAgent(A2AServer):
    @skill(
        name="Search",
        description="Smart search that handles both location queries and activity recommendations",
        tags=["location", "coordinates", "geocoding", "activities", "recommendations"],
        examples="Search for 'New York City' or 'restaurants in Paris' or 'outdoor activities in London'"
    )
    def search(self, query: str):
        """Smart search that determines if it's a location or activity query"""
        
        # Check if this is an activity recommendation query
        activity_keywords = [
            "recommend", "activities", "things to do", "attractions", "restaurants", 
            "hotels", "places to visit", "outdoor", "indoor", "sightseeing", 
            "museums", "entertainment", "nightlife", "shopping", "tours"
        ]
        
        is_activity_query = any(keyword in query.lower() for keyword in activity_keywords)
        
        if is_activity_query:
            return self._handle_activity_recommendation(query)
        else:
            return self._handle_location_search(query)
    
    def _handle_activity_recommendation(self, query: str):
        """Handle activity and recommendation queries with predefined suggestions"""
        query_lower = query.lower()
        
        # Extract location from the query
        location = self._extract_location_from_query(query)
        
        # Generate activity recommendations based on query type
        if "outdoor" in query_lower:
            activities = self._get_outdoor_activities(location)
        elif "indoor" in query_lower:
            activities = self._get_indoor_activities(location)
        elif "restaurant" in query_lower or "food" in query_lower:
            activities = self._get_restaurant_recommendations(location)
        elif "museum" in query_lower:
            activities = self._get_museum_recommendations(location)
        else:
            activities = self._get_general_activities(location)
        
        return f"Activity recommendations for {location}:\n\n{activities}"
    
    def _extract_location_from_query(self, query: str):
        """Extract location from activity query"""
        # Common patterns: "activities in Paris", "recommend restaurants in Tokyo"
        if " in " in query:
            location = query.split(" in ")[-1].strip().rstrip("?.")
            return location
        elif " for " in query:
            location = query.split(" for ")[-1].strip().rstrip("?.")
            return location
        else:
            # Try to find location at the end
            words = query.split()
            return words[-1] if words else "the location"
    
    def _get_outdoor_activities(self, location):
        """Get outdoor activity recommendations"""
        activities = {
            "paris": [
                "Seine River cruise and walk along the riverbank",
                "Picnic in Luxembourg Gardens or Tuileries Garden", 
                "Climb the Eiffel Tower for panoramic city views",
                "Explore Montmartre district and Sacré-Cœur Basilica",
                "Bike tour through the Marais district",
                "Walking tour of the Latin Quarter"
            ],
            "london": [
                "Hyde Park and Speaker's Corner visit",
                "Thames River walking path and Tower Bridge",
                "Camden Market and Regent's Canal walk",
                "Greenwich Park and Royal Observatory",
                "Hampstead Heath for city views",
                "Covent Garden street performances"
            ],
            "tokyo": [
                "Cherry blossom viewing in Ueno Park",
                "Senso-ji Temple in Asakusa district",
                "Shibuya Crossing experience",
                "Harajuku and Takeshita Street exploration",
                "Imperial Palace East Gardens",
                "Odaiba Beach and Rainbow Bridge"
            ]
        }
        
        location_key = location.lower()
        if location_key in activities:
            return "\n".join(f"• {activity}" for activity in activities[location_key])
        else:
            return f"• Explore local parks and outdoor markets\n• Walking tours of historic districts\n• Riverfront or waterfront areas\n• Local hiking trails or scenic viewpoints\n• Outdoor cafés and street food areas\n• Public gardens and green spaces"
    
    def _get_indoor_activities(self, location):
        """Get indoor activity recommendations"""
        activities = {
            "paris": [
                "Louvre Museum - see the Mona Lisa and Venus de Milo",
                "Musée d'Orsay for Impressionist masterpieces",
                "Palace of Versailles (day trip from Paris)",
                "Sainte-Chapelle for stunning stained glass",
                "Shopping at Galeries Lafayette and Printemps",
                "Les Invalides and Napoleon's Tomb"
            ],
            "london": [
                "British Museum and Rosetta Stone",
                "Tate Modern art gallery",
                "Westminster Abbey and Houses of Parliament tour",
                "Shopping in Oxford Street and Covent Garden",
                "National Gallery in Trafalgar Square",
                "Borough Market for food tasting"
            ],
            "tokyo": [
                "Tokyo National Museum in Ueno",
                "Meiji Shrine indoor areas",
                "Tsukiji Outer Market food halls",
                "Department stores in Ginza (Mitsukoshi, Ginza Six)",
                "Akihabara electronics and anime culture",
                "Traditional tea ceremony experience"
            ]
        }
        
        location_key = location.lower()
        if location_key in activities:
            return "\n".join(f"• {activity}" for activity in activities[location_key])
        else:
            return f"• Local museums and art galleries\n• Historic buildings and monuments\n• Shopping centers and markets\n• Cultural centers and theaters\n• Traditional craft workshops\n• Local cuisine cooking classes"
    
    def _get_restaurant_recommendations(self, location):
        """Get restaurant recommendations"""
        return f"• Local traditional cuisine restaurants\n• Highly-rated cafés and bistros\n• Food markets with local specialties\n• Rooftop restaurants with city views\n• Historic restaurants with cultural significance\n• Street food vendors and food halls"
    
    def _get_museum_recommendations(self, location):
        """Get museum recommendations"""
        return f"• National and history museums\n• Art galleries featuring local artists\n• Science and technology museums\n• Cultural heritage centers\n• Archaeological museums\n• Contemporary art spaces"
    
    def _get_general_activities(self, location):
        """Get general activity recommendations"""
        return f"• Top historical landmarks and monuments\n• Local markets and shopping districts\n• Traditional cultural experiences\n• Popular viewpoints and photo spots\n• Local food specialties and restaurants\n• Walking tours of historic neighborhoods"
    
    def _handle_location_search(self, query: str):
        """Handle pure location search using Nominatim API"""
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 5,
            "addressdetails": 1,
            "extratags": 1
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                return f"No location results found for '{query}'."
            
            results = []
            for result in data:
                display_name = result.get("display_name", "Unknown location")
                lat = result.get("lat", "N/A")
                lon = result.get("lon", "N/A")
                place_type = result.get("type", "location")
                importance = result.get("importance", 0)
                
                results.append(f"- {display_name}")
                results.append(f"  Type: {place_type}")
                results.append(f"  Coordinates: {lat}, {lon}")
                results.append(f"  Importance: {importance:.3f}")
                results.append("")
            
            summary = "\n".join(results)
            return f"Location search results for '{query}':\n\n{summary}"
            
        except requests.RequestException as e:
            logging.error(f"Error during location search: {e}")
            return f"Location search failed: {e}"
        except Exception as e:
            return f"Unexpected error during location search: {e}"

    def handle_task(self, task):
        message_data = task.message or {}
        content = message_data.get("content", {})
        text = content.get("text", "") if isinstance(content, dict) else ""
        
        if text.strip():
            # Use Nominatim API for all searches
            result = self.search(text.strip())
            
            task.artifacts = [{
                "parts": [{"type": "text", "text": result}]
            }]
            task.status = TaskStatus(state=TaskState.COMPLETED)
        else:
            task.status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message={"role": "agent", "content": {"type": "text", 
                         "text": "Please provide a search query or location to find."}}
            )
        return task
if __name__ == "__main__":
    agent = LocationSearchAgent(google_a2a_compatible=True)
    run_server(agent, port=8002, debug=True)