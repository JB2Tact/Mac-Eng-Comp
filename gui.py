# gui.py
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QTextEdit, QComboBox
from PyQt5.QtCore import Qt
from main import generate_sample_buildings, initialize_agents, compute_routes, geocode_location

class SimulationApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Government Simulation Program")
        self.setGeometry(100, 100, 800, 600)

        # Create layout
        self.layout = QVBoxLayout()

        # Create labels and textboxes
        self.output_label = QLabel("Output:")
        self.layout.addWidget(self.output_label)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.layout.addWidget(self.output_text)

        # Add a dropdown to select agent type
        self.agent_type_selector = QComboBox()
        self.agent_type_selector.addItem("Truck")
        self.agent_type_selector.addItem("Drone")
        self.agent_type_selector.addItem("Volunteer")
        self.layout.addWidget(self.agent_type_selector)

        # Add buttons for various tasks
        self.generate_buildings_button = QPushButton("Generate Buildings")
        self.generate_buildings_button.clicked.connect(self.generate_buildings)
        self.layout.addWidget(self.generate_buildings_button)

        self.initialize_agents_button = QPushButton("Initialize Agents")
        self.initialize_agents_button.clicked.connect(self.initialize_agents)
        self.layout.addWidget(self.initialize_agents_button)

        self.compute_routes_button = QPushButton("Compute Routes")
        self.compute_routes_button.clicked.connect(self.compute_routes)
        self.layout.addWidget(self.compute_routes_button)

        # Set the layout for the main window
        self.setLayout(self.layout)

    def display_output(self, text):
        """Helper method to append text to the output text box"""
        self.output_text.append(text)

    def generate_buildings(self):
        self.display_output("Generating buildings...")
        buildings = generate_sample_buildings(num_buildings=30)
        self.display_output(f"Generated {len(buildings)} buildings.")

    def initialize_agents(self):
        center_coords = geocode_location("Pasadena, California, USA")
        if not center_coords:
            center_coords = [-118.1445, 34.1478]  # Default to Pasadena center
        self.agents = initialize_agents(center_coords)
        self.display_output(f"Initialized {len(self.agents)} agents.")

    def compute_routes(self):
        if not hasattr(self, 'agents'):
            self.display_output("Please initialize agents first.")
            return
        self.display_output("Computing routes...")
        compute_routes(self.agents)
        total_distance = sum(agent['route']['distance'] for agent in self.agents if agent['route'])
        total_duration = sum(agent['route']['duration'] for agent in self.agents if agent['route'])
        self.display_output(f"Total distance: {total_distance / 1000:.1f} km")
        self.display_output(f"Total time: {total_duration / 60:.1f} minutes")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SimulationApp()
    window.show()
    sys.exit(app.exec_())
