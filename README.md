# A2A Travel Agent 🌍✈️

A multi-agent travel planning system built with Python-A2A that combines weather forecasting, location search, and AI-powered recommendations to create personalized travel plans.

## 🏗️ Architecture

This project demonstrates a distributed agent architecture where specialized agents work together:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Weather Agent │    │  Location Search │    │   LLM Agent     │
│   Port: 8001    │    │     Agent        │    │   Port: 5001    │
│                 │    │   Port: 8002     │    │                 │
│ • Open-Meteo    │    │ • Nominatim API  │    │ • LLaMA 3.2     │
│   API           │    │ • Activity Recs  │    │ • Ollama        │
│ • Forecasting   │    │ • Geocoding      │    │ • Summarization │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                   ┌─────────────────────────┐
                   │  Travel Planner Agent   │
                   │  (Main Orchestrator)    │
                   │                         │
                   │ • Agent Network         │
                   │ • Flow Coordination     │
                   │ • Result Synthesis      │
                   └─────────────────────────┘
```

## 🚀 Features

- **Multi-Agent Coordination**: Uses Python-A2A framework for seamless agent communication
- **Weather-Aware Planning**: Automatically adjusts activity recommendations based on weather conditions
- **Location Intelligence**: Uses OpenStreetMap's Nominatim API for geocoding and location search
- **Predefined Activity Recommendations**: Curated suggestions for popular destinations (Paris, London, Tokyo) with fallback to generic recommendations
- **AI-Powered Synthesis**: Uses local LLaMA 3.2 model for creating comprehensive travel summaries
- **Flexible Architecture**: Each agent runs independently and can be scaled horizontally

## 📋 Prerequisites

- Python 3.8+
- Ollama with LLaMA 3.2 model installed
- Virtual environment (recommended)
- Internet connection for weather and location APIs

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd "A2A Travel Agent"
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv env
   env\Scripts\activate  # Windows
   # source env/bin/activate  # Linux/Mac
   ```

3. **Install dependencies**
   ```bash
   pip install python-a2a langchain-ollama langchain-core requests
   ```

4. **Install Ollama and LLaMA 3.2**
   ```bash
   # Download Ollama from https://ollama.ai/
   ollama pull llama3.2:latest
   ```

5. **Set up environment (optional)**
   The current implementation doesn't require API keys, but you can create a `.env` file for future enhancements:
   ```env
   # Future use for additional APIs
   # BRAVE_API_KEY=your_api_key_here
   ```

## 🏃‍♂️ Running the System

The system requires running multiple agents simultaneously. Open 4 separate terminal windows:

### Terminal 1: Weather Agent
```bash
python WeatherAgent.py
```
*Starts weather service on port 8001*

### Terminal 2: Location Search Agent
```bash
python BraveSearchAgent.py
```
*Starts location search service on port 8002*

### Terminal 3: LLM Agent
```bash
python local_llm.py
```
*Starts LLaMA 3.2 service on port 5001*

### Terminal 4: Travel Planner (Main)
```bash
python Travel_Planner_Agent.py
```
*Orchestrates all agents and generates travel plan*

## 📊 How It Works

### 1. Agent Network Setup
```python
network = AgentNetwork(name="Travel Assistant Network")
network.add("weather", "http://localhost:8001")
network.add("search", "http://localhost:8002")
```

### 2. Weather-Based Decision Making
```python
forecast = weather_agent.ask(f"What's the weather in {destination}?")
if "sunny" in forecast.lower() or "clear" in forecast.lower():
    activities = search_agent.ask(f"Recommend outdoor activities in {destination}")
else:
    activities = search_agent.ask(f"Recommend indoor activities in {destination}")
```

### 3. AI-Powered Synthesis
```python
prompt = f"Based on weather forecast {forecast} and recommendations {activities}, 
          suggest must-see attractions for {travel_dates}."
travel_plan = llm_client.ask(prompt)
```

## 🧩 Component Details

### WeatherAgent.py
- **API**: Open-Meteo (free weather API)
- **Features**: Current conditions, forecasts, geocoding
- **Skills**: `get_weather(location, forecast_days, include_current, include_hourly, include_daily)`
- **Temperature**: Returns temperatures in Fahrenheit
- **Data**: Includes humidity, wind speed, precipitation, and weather conditions

### BraveSearchAgent.py (LocationSearchAgent)
- **Primary API**: OpenStreetMap Nominatim (free geocoding API)
- **Features**: Location search, geocoding, predefined activity recommendations
- **Skills**: `search(query)` - handles both location and activity queries
- **Activity Database**: Curated recommendations for Paris, London, Tokyo
- **Fallback**: Generic recommendations for other locations

### local_llm.py
- **Model**: LLaMA 3.2 via Ollama
- **Features**: Text generation, travel plan synthesis
- **Integration**: LangChain → A2A Server conversion
- **Threading**: Runs in background with graceful shutdown

### Travel_Planner_Agent.py
- **Role**: Main orchestrator
- **Features**: Agent coordination, flow management, result synthesis
- **Logic**: Weather-based activity selection (sunny → outdoor, otherwise → indoor)

## 🎯 Example Output

```
Available Agents:
- weather: Provides comprehensive weather information including current conditions and forecasts
- search: Provides location search, geocoding, and activity recommendations for travel planning

Weather forecast: Weather forecast for Paris, France
==================================================

CURRENT CONDITIONS:
Temperature: 72°F
Humidity: 65%
Wind Speed: 8 mph
Wind Direction: 270°
Conditions: Partly cloudy

DAILY FORECAST:
Friday, June 21:
  High: 75°F, Low: 58°F
  Conditions: Partly cloudy
  Precipitation: 0.0 in
  Max Wind: 12 mph

Prompt: You are a travel assistant. Based on the weather forecast result [...] 
and the recommendations [Seine River cruise and walk along the riverbank...], 
suggest me a few must-see attractions on date June 21-25.

LLM response: Based on the pleasant weather forecast for June 21-25 in Paris, 
here's your perfect itinerary:

🌞 **June 21-25 Paris Adventure**
- **Day 1**: Seine River cruise & Eiffel Tower visit
- **Day 2**: Luxembourg Gardens picnic & Latin Quarter exploration
- **Day 3**: Montmartre walking tour & Sacré-Cœur
- **Day 4**: Louvre Museum & Tuileries Garden stroll
- **Day 5**: Versailles day trip (outdoor gardens perfect for the weather)

The partly cloudy skies are ideal for photography and outdoor exploration!
```

## 🔧 Configuration

### Customizing Destinations
Edit the `params` dictionary in `Travel_Planner_Agent.py`:
```python
params = {
    "destination": "Tokyo",        # Change destination
    "travel_dates": "July 1-7"    # Change dates
}
```

### Adding New Activity Recommendations
Edit the activity dictionaries in `BraveSearchAgent.py`:
```python
def _get_outdoor_activities(self, location):
    activities = {
        "your_city": [
            "Activity 1",
            "Activity 2",
            # Add more activities
        ],
        # Add new cities
    }
```

### Adjusting Weather Sensitivity
Modify the weather condition logic in `Travel_Planner_Agent.py`:
```python
# Add more weather conditions
if any(condition in forecast.lower() for condition in ["sunny", "clear", "partly cloudy"]):
    activities = search_agent.ask(f"Recommend outdoor activities in {destination}")
```

### LLM Model Selection
Change the model in `local_llm.py`:
```python
llm = OllamaLLM(model="llama3.1:latest")  # or other models
```

## 🔍 Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   netstat -ano | findstr :8001  # Check port usage
   taskkill /PID <PID> /F        # Kill process if needed
   ```

2. **Weather API Timeout**
   - Open-Meteo API is free but may have rate limits
   - Check internet connection
   - Try reducing forecast_days parameter

3. **Ollama Connection Issues**
   ```bash
   ollama list                    # Check installed models
   ollama serve                   # Start Ollama service
   ollama pull llama3.2:latest   # Ensure model is installed
   ```

4. **Agent Connection Timeouts**
   - Ensure all agents are running before starting Travel_Planner_Agent.py
   - Check firewall settings for localhost ports
   - Verify no other applications are using ports 8001, 8002, 5001

5. **Missing Dependencies**
   ```bash
   pip install --upgrade python-a2a langchain-ollama langchain-core requests
   ```

## 🧪 Testing Individual Agents

### Test Weather Agent
```python
from python_a2a import A2AClient
weather_client = A2AClient("http://localhost:8001")
result = weather_client.ask("Get weather for London")
print(result)
```

### Test Location Search Agent
```python
from python_a2a import A2AClient
search_client = A2AClient("http://localhost:8002")
result = search_client.ask("Recommend outdoor activities in Paris")
print(result)
```

### Test LLM Agent
```python
from python_a2a import A2AClient
llm_client = A2AClient("http://localhost:5001")
result = llm_client.ask("Suggest a travel itinerary for Tokyo")
print(result)
```

## 📝 Current Limitations

- **Activity Database**: Limited to Paris, London, and Tokyo with predefined recommendations
- **Weather Dependency**: Simple sunny/not-sunny logic for activity selection
- **No Real-time Search**: Uses predefined activity lists instead of live web search
- **Single Language**: Only supports English
- **No Persistence**: No database to store user preferences or history

## 🔮 Future Enhancements

- [ ] **Real Web Search**: Integrate actual Brave Search API or similar service
- [ ] **Expanded Activity Database**: Add more cities and dynamic recommendations
- [ ] **Flight Integration**: Add flight booking agent using airline APIs
- [ ] **Hotel Recommendations**: Integrate accommodation search
- [ ] **Currency Conversion**: Add real-time exchange rates
- [ ] **Language Translation**: Multi-language support for international travel
- [ ] **Calendar Integration**: Sync with Google Calendar/Outlook
- [ ] **Budget Planning**: Cost estimation and budget tracking
- [ ] **Real-time Updates**: WebSocket connections for live updates
- [ ] **User Preferences**: Personalized recommendations based on user history
- [ ] **Advanced Weather Logic**: More sophisticated weather-based recommendations

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 🆘 Support

If you encounter any issues or have questions:
- Create an issue on GitHub
- Check the troubleshooting section above
- Review Python-A2A documentation at [https://python-a2a.readthedocs.io/](https://python-a2a.readthedocs.io/)

---

**Built with ❤️ using Python-A2A, LangChain, and Ollama**
