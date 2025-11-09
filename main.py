import requests
import json
from math import radians, cos, sin, asin, sqrt
import random
import os
from dotenv import load_dotenv

# Try to import Gemini API
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️  google-generativeai package not installed. Install with: pip install google-generativeai")


# Load environment variables from .env file
load_dotenv()

# -----------------------------
# Configuration
# -----------------------------
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
place_name = "Pasadena, California, USA"

# Configure Gemini API
if GEMINI_API_KEY and GEMINI_AVAILABLE:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"⚠️  Failed to configure Gemini API: {e}")

# Pasadena, CA bounding box (approximate)
BBOX = {
    "min_lon": -118.198,
    "max_lon": -118.065,
    "min_lat": 34.119,
    "max_lat": 34.220
}

# -----------------------------
# 1️⃣ Helper Functions
# -----------------------------
def haversine_distance(lon1, lat1, lon2, lat2): # uses the haversine distance formula to calculate distance between two lat/lon points 
    #basically means the shortest distance over the earth's surface (used for a drone because it flies and not on roads)
    """Calculate distance between two points in meters"""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2]) # lon is longitude, lat is latitude
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2 # formula 
    c = 2 * asin(sqrt(a))
    r = 6371000  # Radius of earth in meters
    return c * r

def get_mapbox_directions(start_coords, end_coords, profile='driving'):
    """
    Get routing directions from Mapbox Directions API
    profile: 'driving', 'walking', 'cycling', 'driving-traffic'
    coords format: [lon, lat]
    """
    url = f"https://api.mapbox.com/directions/v5/mapbox/{profile}/{start_coords[0]},{start_coords[1]};{end_coords[0]},{end_coords[1]}"
    
    params = {
        'access_token': MAPBOX_ACCESS_TOKEN,
        'geometries': 'geojson',
        'overview': 'full',
        'steps': 'true'
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200: #calling the mapbox directions api to get route info
        data = response.json()
        if data['routes']:
            route = data['routes'][0]
            return {
                'geometry': route['geometry']['coordinates'],  # List of [lon, lat] points
                'distance': route['distance'],  # meters
                'duration': route['duration'],  # seconds
                'steps': route['legs'][0]['steps']
            }
    return None

def get_mapbox_isochrone(center_coords, minutes=10, profile='driving'):
    """
    Get isochrone (reachable area) from Mapbox Isochrone API
    Useful for coverage analysis
    """
    url = f"https://api.mapbox.com/isochrone/v1/mapbox/{profile}/{center_coords[0]},{center_coords[1]}"
    
    params = {
        'contours_minutes': minutes,
        'polygons': 'true',
        'access_token': MAPBOX_ACCESS_TOKEN
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        return response.json()
    return None

def geocode_location(place_name):
    """Geocode a place name to coordinates using Mapbox Geocoding API"""
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{place_name}.json"
    
    params = {
        'access_token': MAPBOX_ACCESS_TOKEN,
        'limit': 1
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data['features']:
            coords = data['features'][0]['center']  # [lon, lat]
            return coords
    return None


# Alternatively, you can use Mapbox Tilequery API to get real building data
def get_buildings_from_mapbox(center_coords, radius=1000):
    """
    Get building footprints from Mapbox using Tilequery API
    Note: This requires a dataset with building data
    """
    url = f"https://api.mapbox.com/v4/mapbox.mapbox-streets-v8/tilequery/{center_coords[0]},{center_coords[1]}.json"
    
    params = {
        'radius': radius,
        'limit': 50,
        'access_token': MAPBOX_ACCESS_TOKEN,
        'layers': 'building'
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        buildings = []
        for feature in data.get('features', []):
            coords = feature['geometry']['coordinates']
            buildings.append({
                'id': feature['id'],
                'lon': coords[0] if len(coords) == 2 else coords[0][0],
                'lat': coords[1] if len(coords) == 2 else coords[0][1],
                'type': feature['properties'].get('type', 'unknown')
            })
        return buildings
    
    return []

# -----------------------------
# 3️⃣ Initialize Agents
# -----------------------------
def initialize_agents(center_coords, num_trucks=5, num_drones=3, num_volunteers=10):
    """Initialize all agents at a central location"""
    agents = []
    
    for i in range(num_trucks):
        agents.append({
            'id': f'truck_{i}',
            'type': 'truck',
            'current_coords': center_coords.copy(),
            'target_building': None,
            'route': None,
            'profile': 'driving'
        })
    
    for i in range(num_drones):
        agents.append({
            'id': f'drone_{i}',
            'type': 'drone',
            'current_coords': center_coords.copy(),
            'target_building': None,
            'route': None,
            'profile': None  # Drones fly straight line
        })
    
    for i in range(num_volunteers):
        agents.append({
            'id': f'volunteer_{i}',
            'type': 'volunteer',
            'current_coords': center_coords.copy(),
            'target_building': None,
            'route': None,
            'profile': 'walking'
        })
    
    return agents


def assign_buildings_to_agents(agents, buildings):
    """Simple round-robin assignment of buildings to agents"""
    for i, agent in enumerate(agents):
        building = buildings[i % len(buildings)]
        agent['target_building'] = building
        print(f"Assigned {building['id']} to {agent['id']}")

# -----------------------------
# 5️⃣ Compute Routes
# -----------------------------
def compute_routes(agents):
    """Compute optimal routes for all agents (recalculates routes each time)"""
    # Clear all previous routes to ensure fresh calculation
    for agent in agents:
        agent['route'] = None
    
    for agent in agents:
        if agent['target_building'] is None:
            continue
        
        start = agent['current_coords']
        end = [agent['target_building']['lon'], agent['target_building']['lat']]
        
        building = agent['target_building']
        fire_info = ""
        if building and building.get('has_fire', False):
            fire_info = f" 🔥 FIRE ({building.get('fire_severity', 'unknown').upper()})"
        
        if agent['type'] == 'drone':
            # Drones fly straight line - just calculate distance
            distance = haversine_distance(start[0], start[1], end[0], end[1])
            agent['route'] = {
                'geometry': [start, end],
                'distance': distance,
                'duration': distance / 15,  # Assume 15 m/s flight speed
                'type': 'straight_line'
            }
            print(f"\n{agent['id']} (Drone) - Straight line flight{fire_info}:")
            print(f"  Target: {building['id'] if building else 'None'}")
            print(f"  Distance: {distance:.0f}m")
            print(f"  Duration: {distance/15:.0f}s")
        else:
            # Road-based agents use Mapbox Directions API
            route = get_mapbox_directions(start, end, profile=agent['profile'])
            
            if route:
                agent['route'] = route
                print(f"\n{agent['id']} ({agent['type'].capitalize()}) - Road route{fire_info}:")
                print(f"  Target: {building['id'] if building else 'None'}")
                print(f"  Distance: {route['distance']:.0f}m")
                print(f"  Duration: {route['duration']:.0f}s")
                print(f"  Waypoints: {len(route['geometry'])} points")
            else:
                print(f"\n{agent['id']} - Failed to get route{fire_info}")

# -----------------------------
# 7️⃣ New Features: Priority and Agent Speeds
# -----------------------------

# Realistic average speeds (m/s) for agents
AGENT_SPEEDS = {
    'truck': 12,       # ~43 km/h
    'drone': 15,       # ~54 km/h
    'volunteer': 2.5   # ~9 km/h walking
}

# Fire severity levels and their multipliers
FIRE_SEVERITY = {
    'none': 0,
    'low': 1,
    'medium': 3,
    'high': 5,
    'critical': 10
}

def get_optimal_agent_type_for_fire_severity(severity):
    """
    Use Gemini API to determine the most effective agent type for a given fire severity.
    Returns: 'volunteer', 'truck', or 'drone'
    """
    if not GEMINI_API_KEY or not GEMINI_AVAILABLE:
        # Fallback logic if Gemini API is not available
        if severity == 'low':
            return 'volunteer'
        elif severity == 'medium':
            return 'truck'
        else:  # high or critical
            return 'drone'
    
    try:
        # Create the model
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""You are an emergency response coordinator. For a {severity} severity fire at a building, determine which type of response agent would be most effective:

Available agents:
- Volunteer: Walking speed (~2.5 m/s), can handle basic tasks, first aid, evacuation assistance
- Truck: Driving speed (~12 m/s), carries firefighting equipment, water, can handle medium fires
- Drone: Flying speed (~15 m/s), fastest response, can assess situation, deliver small supplies, but limited firefighting capability

Fire severity levels:
- Low: Small fire, contained, minimal risk
- Medium: Moderate fire, spreading, some risk
- High: Large fire, spreading rapidly, high risk
- Critical: Major fire, out of control, extreme risk

For a {severity} severity fire, which agent type would be MOST EFFECTIVE? Consider:
1. Response time urgency
2. Firefighting capability needed
3. Equipment requirements
4. Risk level

Respond with ONLY one word: 'volunteer', 'truck', or 'drone'"""
        
        response = model.generate_content(prompt)
        result = response.text.strip().lower()
        
        # Validate and return result
        if 'volunteer' in result:
            return 'volunteer'
        elif 'truck' in result:
            return 'truck'
        elif 'drone' in result:
            return 'drone'
        else:
            # Fallback if response is unclear
            if severity == 'low':
                return 'volunteer'
            elif severity == 'medium':
                return 'truck'
            else:
                return 'drone'
                
    except Exception as e:
        print(f"   ⚠️  Gemini API error: {e}. Using fallback logic.")
        # Fallback logic
        if severity == 'low':
            return 'volunteer'
        elif severity == 'medium':
            return 'truck'
        else:
            return 'drone'

def get_optimal_agent_mapping():
    """
    Get optimal agent type mapping for each fire severity level using Gemini.
    Returns a dictionary mapping severity to optimal agent type.
    """
    print(f"\n🤖 Consulting Gemini AI for optimal agent assignments...")
    mapping = {}
    
    for severity in ['low', 'medium', 'high', 'critical']:
        optimal_type = get_optimal_agent_type_for_fire_severity(severity)
        mapping[severity] = optimal_type
        print(f"   {severity.upper()} fire → {optimal_type.capitalize()}")
    
    return mapping

def generate_fires(buildings, fire_probability=0.3):
    """
    Randomly assign fires to buildings
    fire_probability: probability that a building has a fire (0.0 to 1.0)
    """
    fire_count = 0
    for building in buildings:
        if random.random() < fire_probability:
            # Randomly assign fire severity
            severity = random.choices(
                ['low', 'medium', 'high', 'critical'],
                weights=[0.4, 0.3, 0.2, 0.1]  # More low/medium fires, fewer critical
            )[0]
            building['has_fire'] = True
            building['fire_severity'] = severity
            building['fire_intensity'] = random.uniform(0.5, 1.0)  # Intensity within severity level
            fire_count += 1
        else:
            building['has_fire'] = False
            building['fire_severity'] = 'none'
            building['fire_intensity'] = 0.0
    
    return fire_count

def add_agent_speeds(agents):
    """Add speed attribute to each agent"""
    for agent in agents:
        agent['speed'] = AGENT_SPEEDS.get(agent['type'], 1)  # default 1 m/s

def add_priority_scores(buildings, center_coords):
    """
    Assign a priority score to buildings based on fire status, type, and distance.
    Buildings with fires get much higher priority.
    """
    BUILDING_TYPE_WEIGHT = {'residential': 1.0, 'commercial': 1.5, 'mixed': 1.2}
    
    for building in buildings:
        distance_to_center = haversine_distance(
            building['lon'], building['lat'],
            center_coords[0], center_coords[1]
        )
        
        # Base score from building type and distance
        base_score = BUILDING_TYPE_WEIGHT.get(building.get('type', 'unknown'), 1.0) / (distance_to_center + 1)
        
        # Fire multiplier - buildings with fires get massive priority boost
        if building.get('has_fire', False):
            fire_multiplier = FIRE_SEVERITY.get(building.get('fire_severity', 'low'), 1)
            fire_intensity = building.get('fire_intensity', 0.5)
            # Fire priority = severity * intensity * large multiplier
            fire_priority = fire_multiplier * fire_intensity * 100
            building['priority_score'] = base_score + fire_priority
        else:
            # Non-fire buildings get lower priority
            building['priority_score'] = base_score * 0.1
    
    # Sort buildings by descending priority (fires first!)
    buildings.sort(key=lambda b: b['priority_score'], reverse=True)

def assign_by_priority(agents, buildings, optimal_agent_mapping=None):
    """
    Assign buildings to agents based on priority and Gemini's optimal agent recommendations.
    For buildings with fires, match them to the optimal agent type recommended by Gemini.
    """
    unassigned = buildings.copy()
    assigned_count = 0
    
    # First, assign buildings with fires to optimal agent types
    if optimal_agent_mapping:
        fire_buildings = [b for b in unassigned if b.get('has_fire', False)]
        fire_buildings.sort(key=lambda b: b['priority_score'], reverse=True)
        
        for building in fire_buildings:
            severity = building.get('fire_severity', 'low')
            optimal_type = optimal_agent_mapping.get(severity, 'truck')
            
            # Find an available agent of the optimal type
            matching_agent = None
            for agent in agents:
                if agent['type'] == optimal_type and agent.get('target_building') is None:
                    matching_agent = agent
                    break
            
            # If no agent of optimal type available, use any available agent
            if not matching_agent:
                for agent in agents:
                    if agent.get('target_building') is None:
                        matching_agent = agent
                        break
            
            if matching_agent:
                matching_agent['target_building'] = building
                matching_agent['route'] = None
                unassigned.remove(building)
                assigned_count += 1
                
                fire_info = f" 🔥 FIRE ({severity.upper()})"
                optimal_info = f" [Optimal: {optimal_type.capitalize()}, Assigned: {matching_agent['type'].capitalize()}]"
                match_status = "✓" if matching_agent['type'] == optimal_type else "⚠"
                print(f"{match_status} Assigned {building['id']} (priority={building['priority_score']:.2f}){fire_info}{optimal_info} to {matching_agent['id']}")
    
    # Then assign remaining buildings (non-fire or unmatched fire buildings)
    remaining_agents = [a for a in agents if a.get('target_building') is None]
    for agent in remaining_agents:
        if not unassigned:
            break
        building = unassigned.pop(0)
        agent['target_building'] = building
        agent['route'] = None
        
        fire_info = ""
        if building.get('has_fire', False):
            fire_info = f" 🔥 FIRE ({building.get('fire_severity', 'unknown').upper()})"
        print(f"Assigned {building['id']} (priority={building['priority_score']:.2f}){fire_info} to {agent['id']}")
        assigned_count += 1
    
    return assigned_count

def update_route_durations_by_speed(agents):
    """Update route durations using each agent's speed"""
    for agent in agents:
        if agent['route']:
            speed = agent.get('speed', 1)
            agent['route']['duration'] = agent['route']['distance'] / speed


# -----------------------------
# 6️⃣ Main Execution
# -----------------------------
def main():
    print("🚨 Disaster Relief Routing System (Mapbox)")
    print("=" * 50)
    print("🔄 Generating new fires and calculating optimal routes...")
    
    # Get center coordinates for Pasadena
    center_coords = geocode_location(place_name)
    if not center_coords:
        print("Failed to geocode location. Using default coordinates.")
        center_coords = [-118.1445, 34.1478]  # Pasadena center
    
    print(f"\n📍 Center location: {place_name}")
    print(f"   Coordinates: {center_coords}")
    
    # Fetch real building footprints from Mapbox
    print(f"\n🏢 Fetching building locations from Mapbox...")
    buildings = get_buildings_from_mapbox(center_coords, radius=1000)  # radius in meters
    print(f"   Retrieved {len(buildings)} buildings")
    
    # If no buildings found, create some sample buildings
    if len(buildings) == 0:
        print("   No buildings found. Creating sample buildings...")
        buildings = []
        for i in range(30):
            lon = random.uniform(BBOX['min_lon'], BBOX['max_lon'])
            lat = random.uniform(BBOX['min_lat'], BBOX['max_lat'])
            buildings.append({
                'id': f'building_{i}',
                'lon': lon,
                'lat': lat,
                'type': random.choice(['residential', 'commercial', 'mixed'])
            })
        print(f"   Created {len(buildings)} sample buildings")
    
    # Generate random fires on buildings
    print(f"\n🔥 Generating random fires on buildings...")
    fire_count = generate_fires(buildings, fire_probability=0.3)
    print(f"   {fire_count} buildings are on fire!")
    
    # Display fire breakdown
    if fire_count > 0:
        fire_by_severity = {}
        for building in buildings:
            if building.get('has_fire', False):
                severity = building.get('fire_severity', 'unknown')
                fire_by_severity[severity] = fire_by_severity.get(severity, 0) + 1
        print(f"   Fire breakdown:")
        for severity, count in sorted(fire_by_severity.items(), 
                                      key=lambda x: FIRE_SEVERITY.get(x[0], 0), 
                                      reverse=True):
            print(f"     - {severity.upper()}: {count} buildings")
    
    # Initialize agents
    print(f"\n🚛 Initializing agents...")
    agents = initialize_agents(center_coords)
    print(f"   Trucks: {sum(1 for a in agents if a['type'] == 'truck')}")
    print(f"   Drones: {sum(1 for a in agents if a['type'] == 'drone')}")
    print(f"   Volunteers: {sum(1 for a in agents if a['type'] == 'volunteer')}")
    
    # Add speeds to agents
    add_agent_speeds(agents)
    
    # Get optimal agent type recommendations from Gemini
    optimal_agent_mapping = None
    if fire_count > 0:
        optimal_agent_mapping = get_optimal_agent_mapping()
    else:
        print(f"\n🤖 No fires detected. Skipping Gemini AI consultation.")
    
    # Add priority scores to buildings (fires get highest priority)
    print(f"\n📊 Calculating building priorities...")
    add_priority_scores(buildings, center_coords)
    
    # Assign buildings by priority using Gemini's recommendations
    print(f"\n📋 Assigning buildings to agents...")
    if optimal_agent_mapping:
        print(f"   Using Gemini AI recommendations for optimal agent matching...")
    assign_by_priority(agents, buildings, optimal_agent_mapping)
    
    # Compute routes
    print(f"\n🗺️  Computing routes...")
    compute_routes(agents)
    
    # Update route durations based on agent speeds
    update_route_durations_by_speed(agents)
    
    print("\n✅ Route planning complete!")
    
    # Summary statistics
    total_distance = sum(a['route']['distance'] for a in agents if a['route'])
    total_duration = sum(a['route']['duration'] for a in agents if a['route'])
    
    # Fire response statistics
    agents_with_fires = [a for a in agents if a.get('target_building') and a['target_building'].get('has_fire', False)]
    fire_distance = sum(a['route']['distance'] for a in agents_with_fires if a.get('route'))
    fire_duration = sum(a['route']['duration'] for a in agents_with_fires if a.get('route'))
    
    print(f"\n📊 Summary:")
    print(f"   Total distance: {total_distance/1000:.1f} km")
    print(f"   Total time: {total_duration/60:.1f} minutes")
    print(f"   Average per agent: {total_distance/len(agents)/1000:.1f} km")
    
    if agents_with_fires:
        print(f"\n🔥 Fire Response Statistics:")
        print(f"   Agents responding to fires: {len(agents_with_fires)}")
        print(f"   Fire response distance: {fire_distance/1000:.1f} km")
        print(f"   Fire response time: {fire_duration/60:.1f} minutes")
        print(f"   Average time to fire: {fire_duration/len(agents_with_fires)/60:.1f} minutes")
        
        # Show Gemini recommendation matching statistics
        if optimal_agent_mapping:
            optimal_matches = 0
            for agent in agents_with_fires:
                building = agent.get('target_building')
                if building and building.get('has_fire', False):
                    severity = building.get('fire_severity', 'low')
                    optimal_type = optimal_agent_mapping.get(severity, 'truck')
                    if agent['type'] == optimal_type:
                        optimal_matches += 1
            
            match_rate = (optimal_matches / len(agents_with_fires) * 100) if agents_with_fires else 0
            print(f"\n🤖 Gemini AI Recommendation Matching:")
            print(f"   Optimal matches: {optimal_matches}/{len(agents_with_fires)} ({match_rate:.1f}%)")
    
    # Save agents data to JSON
    with open('agents.json', 'w') as f:
        json.dump(agents, f, indent=2)
    print(f"\n💾 Saved agent data to agents.json")

if __name__ == "__main__":
    # Check if tokens are set
    missing_tokens = []
    if not MAPBOX_ACCESS_TOKEN:
        missing_tokens.append("MAPBOX_ACCESS_TOKEN")
    if not GEMINI_API_KEY:
        missing_tokens.append("GEMINI_API_KEY")
    
    if missing_tokens:
        print("⚠️  Missing environment variables:")
        for token in missing_tokens:
            print(f"   - {token}")
        print("\n   Create a .env file with:")
        if "MAPBOX_ACCESS_TOKEN" in missing_tokens:
            print("   MAPBOX_ACCESS_TOKEN=your_token_here")
            print("   Get your token at: https://account.mapbox.com/access-tokens/")
        if "GEMINI_API_KEY" in missing_tokens:
            print("   GEMINI_API_KEY=your_token_here")
            print("   Get your token at: https://makersuite.google.com/app/apikey")
        print("\n   Note: The system will use fallback logic if Gemini API key is missing.")
    else:
        main()
