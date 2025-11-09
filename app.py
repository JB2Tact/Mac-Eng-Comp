# gui.py
import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QTextEdit, QComboBox
from PyQt5.QtCore import Qt
from dotenv import load_dotenv
from main import initialize_agents, compute_routes, geocode_location, haversine_distance, get_mapbox_directions

# Load environment variables
load_dotenv()
MAPBOX_TOKEN = os.getenv("MAPBOX_ACCESS_TOKEN")

class SimulationApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Government Simulation Program")
        self.setGeometry(100, 100, 800, 600)

        # Layout
        self.layout = QVBoxLayout()

        self.output_label = QLabel("Output:")
        self.layout.addWidget(self.output_label)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.layout.addWidget(self.output_text)

        # Agent type selector (optional)
        self.agent_type_selector = QComboBox()
        self.agent_type_selector.addItems(["Truck", "Drone", "Volunteer"])
        self.layout.addWidget(self.agent_type_selector)

        # Buttons
        self.generate_buildings_button = QPushButton("Load Buildings")
        self.generate_buildings_button.clicked.connect(self.load_buildings)
        self.layout.addWidget(self.generate_buildings_button)

        self.initialize_agents_button = QPushButton("Initialize Agents")
        self.initialize_agents_button.clicked.connect(self.initialize_agents)
        self.layout.addWidget(self.initialize_agents_button)

        self.compute_routes_button = QPushButton("Compute Routes")
        self.compute_routes_button.clicked.connect(self.compute_routes)
        self.layout.addWidget(self.compute_routes_button)

        self.setLayout(self.layout)

        # Data holders
        self.buildings = []
        self.agents = []
        self.center_coords = geocode_location("Pasadena, California, USA") or [-118.1445, 34.1478]

    def display_output(self, text):
        self.output_text.append(text)

    def load_buildings(self):
        """Load static buildings (replace with real API if needed)"""
        self.buildings = [
            {"id": "b1", "lon": -118.1445, "lat": 34.1478, "type": "residential"},
            {"id": "b2", "lon": -118.1420, "lat": 34.1485, "type": "commercial"},
            {"id": "b3", "lon": -118.1400, "lat": 34.1490, "type": "mixed"},
        ]
        self.display_output(f"Loaded {len(self.buildings)} buildings.")

    def initialize_agents(self):
        self.agents = initialize_agents(self.center_coords)
        self.display_output(f"Initialized {len(self.agents)} agents.")

        # Assign buildings to agents in round-robin
        for i, agent in enumerate(self.agents):
            if self.buildings:
                agent['target_building'] = self.buildings[i % len(self.buildings)]

    def compute_routes(self):
        if not self.agents or not self.buildings:
            self.display_output("Please load buildings and initialize agents first.")
            return

        self.display_output("Computing routes...")

        for agent in self.agents:
            building = agent.get('target_building')
            if not building:
                continue

            start = agent['current_coords']
            end = [building['lon'], building['lat']]

            # Drones: straight line only
            if agent['type'] == 'drone':
                distance = haversine_distance(start[0], start[1], end[0], end[1])
                agent['route'] = {
                    'geometry': [start, end],
                    'distance': distance,
                    'duration': distance / 15,  # assume 15 m/s for drones
                    'type': 'straight_line'
                }
            else:
                # Try Mapbox if token available
                route = None
                if MAPBOX_TOKEN:
                    try:
                        profile = agent.get('profile', 'driving')
                        route = get_mapbox_directions(start, end, profile)
                    except Exception as e:
                        self.display_output(f"Mapbox API failed: {e}")
                        route = None

                # Fallback to straight-line haversine distance
                if not route:
                    distance = haversine_distance(start[0], start[1], end[0], end[1])
                    speed = 12 if agent['type'] == 'truck' else 2.5  # default speeds
                    route = {
                        'geometry': [start, end],
                        'distance': distance,
                        'duration': distance / speed,
                        'type': 'straight_line'
                    }

                agent['route'] = route

        # Display totals
        total_distance = sum(a['route']['distance'] for a in self.agents if a['route'])
        total_duration = sum(a['route']['duration'] for a in self.agents if a['route'])
        self.display_output(f"Total distance: {total_distance / 1000:.2f} km")
        self.display_output(f"Total time: {total_duration / 60:.2f} minutes")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SimulationApp()
    window.show()
    sys.exit(app.exec_())
