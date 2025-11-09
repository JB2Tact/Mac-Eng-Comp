# app.py
from flask import Flask, render_template, jsonify, request
import random
import os
from dotenv import load_dotenv
from main import initialize_agents, compute_routes, geocode_location, haversine_distance

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Default location (Pasadena)
place_name = "Pasadena, California, USA"
center_coords = geocode_location(place_name) or [-118.1445, 34.1478]  # Default coordinates

@app.route('/')
def index():
    return render_template('index.html')  # This will render the web UI

@app.route('/generate_buildings', methods=['GET'])
def generate_buildings():
    buildings = generate_sample_buildings(num_buildings=30)
    return jsonify(buildings)

@app.route('/initialize_agents', methods=['GET'])
def initialize_agents_route():
    agents = initialize_agents(center_coords)
    return jsonify(agents)

@app.route('/compute_routes', methods=['POST'])
def compute_routes_route():
    agents = request.json.get('agents', [])
    compute_routes(agents)
    total_distance = sum(agent['route']['distance'] for agent in agents if agent['route'])
    total_duration = sum(agent['route']['duration'] for agent in agents if agent['route'])
    return jsonify({
        'total_distance': total_distance / 1000,  # km
        'total_duration': total_duration / 60,   # minutes
        'agents': agents
    })

if __name__ == '__main__':
    app.run(debug=True)
