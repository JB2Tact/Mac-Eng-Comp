import requests
import json
from math import radians, cos, sin, asin, sqrt
import random
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# -----------------------------
# Configuration
# -----------------------------
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
place_name = "Pasadena, California, USA"

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
def haversine_distance(lon1, lat1, lon2, lat2):
    """Calculate distance between two points in meters"""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
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
    
    if response.status_code == 200:
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
    """Compute optimal routes for all agents"""
    for agent in agents:
        if agent['target_building'] is None:
            continue
        
        start = agent['current_coords']
        end = [agent['target_building']['lon'], agent['target_building']['lat']]
        
        if agent['type'] == 'drone':
            # Drones fly straight line - just calculate distance
            distance = haversine_distance(start[0], start[1], end[0], end[1])
            agent['route'] = {
                'geometry': [start, end],
                'distance': distance,
                'duration': distance / 15,  # Assume 15 m/s flight speed
                'type': 'straight_line'
            }
            print(f"\n{agent['id']} (Drone) - Straight line flight:")
            print(f"  Distance: {distance:.0f}m")
            print(f"  Duration: {distance/15:.0f}s")
        else:
            # Road-based agents use Mapbox Directions API
            route = get_mapbox_directions(start, end, profile=agent['profile'])
            
            if route:
                agent['route'] = route
                print(f"\n{agent['id']} ({agent['type'].capitalize()}) - Road route:")
                print(f"  Distance: {route['distance']:.0f}m")
                print(f"  Duration: {route['duration']:.0f}s")
                print(f"  Waypoints: {len(route['geometry'])} points")
            else:
                print(f"\n{agent['id']} - Failed to get route")

# -----------------------------
# 7️⃣ New Features: Priority and Agent Speeds
# -----------------------------

# Realistic average speeds (m/s) for agents
AGENT_SPEEDS = {
    'truck': 12,       # ~43 km/h
    'drone': 15,       # ~54 km/h
    'volunteer': 2.5   # ~9 km/h walking
}

def add_agent_speeds(agents):
    """Add speed attribute to each agent"""
    for agent in agents:
        agent['speed'] = AGENT_SPEEDS.get(agent['type'], 1)  # default 1 m/s

def add_priority_scores(buildings, center_coords):
    """Assign a priority score to buildings based on type, hazard, and distance"""
    BUILDING_TYPE_WEIGHT = {'residential': 1.0, 'commercial': 1.5, 'mixed': 1.2}
    for building in buildings:
        hazard_intensity = random.uniform(0, 1)  # simulate hazard level
        distance_to_center = haversine_distance(
            building['lon'], building['lat'],
            center_coords[0], center_coords[1]
        )
        building['priority_score'] = hazard_intensity * BUILDING_TYPE_WEIGHT.get(building['type'], 1) / (distance_to_center + 1)
    
    # Sort buildings by descending priority
    buildings.sort(key=lambda b: b['priority_score'], reverse=True)

def assign_by_priority(agents, buildings):
    """Assign buildings in descending priority order to agents"""
    unassigned = buildings.copy()
    for agent in agents:
        if not unassigned:
            break
        building = unassigned.pop(0)
        agent['target_building'] = building
        print(f"Assigned {building['id']} (priority={building['priority_score']:.2f}) to {agent['id']}")

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
    
    # Initialize agents
    print(f"\n🚛 Initializing agents...")
    agents = initialize_agents(center_coords)
    print(f"   Trucks: {sum(1 for a in agents if a['type'] == 'truck')}")
    print(f"   Drones: {sum(1 for a in agents if a['type'] == 'drone')}")
    print(f"   Volunteers: {sum(1 for a in agents if a['type'] == 'volunteer')}")
    
    # Add speeds to agents
    add_agent_speeds(agents)
    
    # Add priority scores to buildings
    add_priority_scores(buildings, center_coords)
    
    # Assign buildings by priority
    print(f"\n📋 Assigning buildings to agents...")
    assign_by_priority(agents, buildings)
    
    # Compute routes
    print(f"\n🗺️  Computing routes...")
    compute_routes(agents)
    
    # Update route durations based on agent speeds
    update_route_durations_by_speed(agents)
    
    print("\n✅ Route planning complete!")
    
    # Summary statistics
    total_distance = sum(a['route']['distance'] for a in agents if a['route'])
    total_duration = sum(a['route']['duration'] for a in agents if a['route'])
    
    print(f"\n📊 Summary:")
    print(f"   Total distance: {total_distance/1000:.1f} km")
    print(f"   Total time: {total_duration/60:.1f} minutes")
    print(f"   Average per agent: {total_distance/len(agents)/1000:.1f} km")
    
    # Save agents data to JSON
    with open('agents.json', 'w') as f:
        json.dump(agents, f, indent=2)
    print(f"\n💾 Saved agent data to agents.json")

if __name__ == "__main__":
    # Check if token is set
    if not MAPBOX_ACCESS_TOKEN:
        print("⚠️  Please set your MAPBOX_ACCESS_TOKEN environment variable")
        print("   Create a .env file with: MAPBOX_ACCESS_TOKEN=your_token_here")
        print("   Or get your token at: https://account.mapbox.com/access-tokens/")
    else:
        main()