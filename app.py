from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from navigation_system.models.node import NavigationGraph
from navigation_system.algorithms.pathfinding import a_star
from navigation_system.models.decision_points import DecisionPointManager
from navigation_system.utils.wifi_scanner import scan_wifi, get_dummy_wifi_data
from navigation_system.algorithms.step_instructions import get_navigation_instructions
from PIL import Image
import os
import sqlite3
import json
import csv

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Required for flash messages

# Dummy credentials
USER_CREDENTIALS = {
    "admin": "password123"
}

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'navigation.db')

# Initialize graph
graph = NavigationGraph()

# Load graph from CSV files
def load_graph_from_csv():
    # Load nodes
    nodes_path = os.path.join(os.path.dirname(__file__), 'navigation_system/point_table.csv')
    if os.path.exists(nodes_path):
        with open(nodes_path, 'r') as csvfile:
            csvreader = csv.reader(csvfile)
            next(csvreader)  # Skip header
            for row in csvreader:
                if len(row) >= 4:
                    graph.add_node(row[0], row[1], 1, row[2], row[3])
    
    # Load edges
    edges_path = os.path.join(os.path.dirname(__file__), 'navigation_system/edge_table.csv')
    if os.path.exists(edges_path):
        with open(edges_path, 'r') as csvfile:
            csvreader = csv.reader(csvfile)
            next(csvreader)  # Skip header
            for row in csvreader:
                if len(row) >= 3:
                    try:
                        graph.add_edge(row[1], row[2])
                    except KeyError:
                        print(f"Warning: Could not add edge between {row[1]} and {row[2]} - nodes not found")

# If CSV files don't exist, create test data
def create_test_graph():
    # Add some test nodes
    graph.add_node("1", "entrance", 1, 100, 100)
    graph.add_node("2", "point", 1, 200, 100)
    graph.add_node("3", "point", 1, 300, 100)
    graph.add_node("4", "point", 1, 300, 200)
    graph.add_node("5", "room", 1, 400, 200)
    
    # Add connections
    graph.add_edge("1", "2")
    graph.add_edge("2", "3")
    graph.add_edge("3", "4")
    graph.add_edge("4", "5")

# Try loading from CSV, fallback to test data
try:
    load_graph_from_csv()
    if not graph.nodes:
        create_test_graph()
except Exception as e:
    print(f"Error loading graph from CSV: {e}")
    create_test_graph()

# Decision points for WiFi fingerprinting
# In a real app, these would be loaded from a database
decision_points = {}  # Format: {node_id: {'description': str, 'fingerprint': {bssid: rssi}}}

# Function to get decision point info
def get_decision_point_info(node_id):
    if node_id in decision_points:
        return {
            'node_id': node_id,
            'description': decision_points[node_id]['description'],
            'is_decision_point': True
        }
    
    # If not a designated decision point, create generic info
    if node_id in graph.nodes:
        node = graph.nodes[node_id]
        return {
            'node_id': node_id,
            'description': f"{node.type_name} {node_id}",
            'is_decision_point': False
        }
    
    return None

# Function to determine if a node is a decision point
def is_decision_point(node_id):
    return node_id in decision_points

# Function to locate user based on WiFi signals
def locate_user(wifi_signals):
    if not wifi_signals or not decision_points:
        # If no fingerprints yet or no signals, return first entrance
        for node_id, node in graph.nodes.items():
            if node.type_name == "entrance":
                return node_id
        # If no entrance found, return first node
        return next(iter(graph.nodes)) if graph.nodes else None
    
    # Find the closest match in our fingerprint database
    best_match = None
    best_score = float('inf')
    
    for node_id, data in decision_points.items():
        fingerprint = data['fingerprint']
        
        # Calculate similarity (lower is better)
        common_bssids = set(wifi_signals.keys()) & set(fingerprint.keys())
        if not common_bssids:
            continue
        
        sum_squared_diff = 0
        for bssid in common_bssids:
            diff = wifi_signals[bssid] - fingerprint[bssid]
            sum_squared_diff += diff * diff
            
        score = (sum_squared_diff / len(common_bssids)) ** 0.5
        
        if score < best_score:
            best_score = score
            best_match = node_id
    
    # Only return a match if the similarity is good enough
    threshold = 10.0  # dBm
    if best_score <= threshold:
        return best_match
    
    return None

# Function to get next decision point along a path
def get_next_decision_point(current_node, path):
    if current_node not in path:
        return None
        
    current_index = path.index(current_node)
    for i in range(current_index + 1, len(path)):
        if path[i] in decision_points:
            return path[i]
            
    # If no more decision points, return the destination
    return path[-1] if path else None
    
# API Endpoints for navigation
@app.route('/api/locate', methods=['POST'])
def api_locate_user():
    """API endpoint to locate user based on WiFi signals"""
    data = request.json
    
    # In a web context, we might not have direct WiFi access,
    # so either use signals from client or dummy data for testing
    wifi_signals = data.get('wifi_signals')
    if not wifi_signals:
        # For testing in browsers where WiFi scanning is restricted
        wifi_signals = get_dummy_wifi_data()
    
    # Find the closest decision point
    node_id = locate_user(wifi_signals)
    
    # For testing - if no match, use manually selected location if provided
    if not node_id and data.get('manual_location'):
        node_id = data.get('manual_location')
    
    # For testing - if still no match, return the first entrance
    if not node_id:
        for id, node in graph.nodes.items():
            if node.type_name == "entrance":
                node_id = id
                break
    
    # If still no node found, use first node
    if not node_id and graph.nodes:
        node_id = next(iter(graph.nodes))
    
    if node_id and node_id in graph.nodes:
        node = graph.nodes[node_id]
        node_info = get_decision_point_info(node_id)
        
        return jsonify({
            'node_id': node_id,
            'x': node.x,
            'y': node.y,
            'description': node_info['description'] if node_info else f"Node {node_id}",
            'success': True
        })
    
    return jsonify({'success': False, 'error': 'Unable to locate user'})

@app.route('/api/nodes')
def api_get_nodes():
    """Get all nodes in the graph"""
    nodes_data = {}
    for node_id, node in graph.nodes.items():
        nodes_data[node_id] = {
            'id': node_id,
            'x': node.x,
            'y': node.y,
            'type': node.type_name,
            'type_name': f"{node.type_name} {node_id}",  # For display
            'is_decision_point': is_decision_point(node_id)
        }
    return jsonify(nodes_data)

@app.route('/api/route', methods=['POST'])
def api_calculate_route():
    """Calculate route between two points"""
    data = request.json
    start_id = data.get('start')
    end_id = data.get('end')
    
    if start_id not in graph.nodes or end_id not in graph.nodes:
        return jsonify({'success': False, 'error': 'Invalid start or end node'})
    
    path = a_star(graph, start_id, end_id)
    
    instructions = get_navigation_instructions(graph, path)
    print("\nNavigation Instructions:")
    for i, instruction in enumerate(instructions, 1):
        print(f"Step {i}: {instruction}")
    
    if not path:
        return jsonify({'success': False, 'error': 'No path found'})
    
    # Convert to coordinates for display
    path_details = []
    for node_id in path:
        node = graph.nodes[node_id]
        is_dp = is_decision_point(node_id)
        
        node_info = {
            'node_id': node_id,
            'x': node.x,
            'y': node.y,
            'is_decision_point': is_dp,
            'description': get_decision_point_info(node_id)['description'] if get_decision_point_info(node_id) else f"{node.type_name} {node_id}"
        }
            
        path_details.append(node_info)
    
    return jsonify({
        'success': True,
        'path': path,
        'path_details': path_details,
        'instructions': instructions
    })

@app.route('/api/next-decision-point', methods=['POST'])
def api_get_next_decision_point():
    """Get the next decision point along a path"""
    data = request.json
    current_id = data.get('current')
    path = data.get('path')
    
    if not current_id or not path:
        return jsonify({'success': False, 'error': 'Missing parameters'})
    
    next_dp = get_next_decision_point(current_id, path)
    
    if next_dp:
        dp_info = get_decision_point_info(next_dp)
        return jsonify({
            'success': True,
            'node_id': next_dp,
            'description': dp_info['description'] if dp_info else f"Node {next_dp}"
        })
    
    # If no next decision point, use the destination
    if path:
        dest_id = path[-1]
        dest_info = get_decision_point_info(dest_id)
        return jsonify({
            'success': True,
            'node_id': dest_id,
            'description': dest_info['description'] if dest_info else f"Destination ({dest_id})"
        })
    
    return jsonify({'success': False, 'error': 'No next decision point found'})

@app.route('/api/fingerprint', methods=['POST'])
def api_add_fingerprint():
    """Add or update a WiFi fingerprint for a location"""
    data = request.json
    node_id = data.get('node_id')
    description = data.get('description')
    wifi_signals = data.get('wifi_signals')
    
    if not node_id or not wifi_signals or node_id not in graph.nodes:
        return jsonify({'success': False, 'error': 'Invalid parameters'})
    
    decision_points[node_id] = {
        'description': description or f"{graph.nodes[node_id].type_name} {node_id}",
        'fingerprint': wifi_signals
    }
    
    return jsonify({'success': True})

@app.route('/')
def home():
    return render_template('home.html', title="Home")

@app.route('/wayfinding')
def wayfinding():
    return render_template('wayfinding.html', title="Wayfinding")

@app.route('/get_directions', methods=['POST'])
def get_directions():
    start = request.form.get('start')
    destination = request.form.get('destination')

    if start and destination:
        flash(f"Finding route from {start} to {destination}...", "info")
        return redirect(url_for('wayfinding'))
    else:
        flash("Please enter both a starting point and a destination!", "danger")
        return redirect(url_for('wayfinding'))
    
@app.route('/settings')
def settings():
    return render_template('settings.html', title="Settings")

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
        flash("Login successful!", "success")
        return redirect(url_for('home'))
    else:
        flash("Invalid credentials!", "danger")
        return redirect(url_for('settings'))
    
if __name__ == '__main__':
    app.run(debug=True)
