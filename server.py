import asyncio
import json
import websockets
from flask import Flask, request, jsonify
import threading
import random

app = Flask(__name__)


@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


# ---------------------------
# Globals
# ---------------------------
connected = set()
async_loop = None
collision_count = 0
goal_reached = False
current_obstacles = []
CANVAS_WIDTH = 650
CANVAS_HEIGHT = 600
robot_state = {'x': 320, 'y': 300, 'angle': 0}


def corner_to_coords(corner: str, margin=20):
    c = corner.upper()
    x = CANVAS_WIDTH - margin if "E" in c else margin
    y = CANVAS_HEIGHT - margin if ("S" in c or "B" in c) else margin
    if c in ("NE", "EN", "TR"): x, y = (CANVAS_WIDTH - margin, margin)
    if c in ("NW", "WN", "TL"): x, y = (margin, margin)
    if c in ("SE", "ES", "BR"): x, y = (CANVAS_WIDTH - margin, CANVAS_HEIGHT - margin)
    if c in ("SW", "WS", "BL"): x, y = (margin, CANVAS_HEIGHT - margin)
    return {"x": x, "y": y}


def generate_random_obstacles(count=8):
    obstacles = []
    for _ in range(count):
        x = random.randint(50, CANVAS_WIDTH - 50)
        y = random.randint(50, CANVAS_HEIGHT - 50)
        obstacles.append({"x": x, "y": y, "size": 25})
    return obstacles


# ---------------------------
# WebSocket Handler (Source of Truth for Robot State)
# ---------------------------
async def ws_handler(websocket, path=None):
    global collision_count, goal_reached, robot_state
    print("Client connected via WebSocket")
    connected.add(websocket)
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if isinstance(data, dict):
                    # THIS IS THE ONLY PLACE THE SERVER'S STATE SHOULD BE UPDATED
                    robot_pos = data.get("robot_position")
                    if robot_pos and 'x' in robot_pos and 'y' in robot_pos:
                        robot_state['x'] = robot_pos['x']
                        robot_state['y'] = robot_pos['y']

                    if data.get("type") == "collision" and data.get("collision"):
                        collision_count += 1
                        print(f"Collision detected! Total: {collision_count}")
                    elif data.get("type") == "goal_reached":
                        goal_reached = True
                        print(f"Goal reached at: {data.get('robot_position')}")
            except Exception as e:
                print(f"Error processing message: {e}")
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    finally:
        connected.remove(websocket)


def broadcast(msg: dict):
    if not connected: return False
    for ws in list(connected):
        try:
            asyncio.run_coroutine_threadsafe(ws.send(json.dumps(msg)), async_loop)
        except Exception as e:
            print(f"Error broadcasting: {e}")
    return True


# ---------------------------
# API Endpoints
# ---------------------------
@app.route('/robot/state', methods=['GET'])
def get_robot_state():
    return jsonify(robot_state)


@app.route('/move', methods=['POST'])
def move():
    global goal_reached
    data = request.get_json()
    if not data or 'x' not in data or 'y' not in data:
        return jsonify({'error': 'Missing parameters "x" and "y".'}), 400

    x, y = data['x'], data['y']
    goal_reached = False

    # REMOVED OPTIMISTIC STATE UPDATE. The server no longer assumes the move succeeds.
    # It waits for the simulator to report the robot's true position.

    msg = {"command": "move", "target": {"x": x, "y": y}}
    if not broadcast(msg):
        return jsonify({'error': 'No connected simulators.'}), 400
    return jsonify({'status': 'move command sent'})


@app.route('/reset', methods=['POST'])
def reset():
    global collision_count, goal_reached, current_obstacles, robot_state
    collision_count = 0
    goal_reached = False
    current_obstacles = []
    robot_state = {'x': 320, 'y': 300, 'angle': 0}

    if not broadcast({"command": "reset"}):
        return jsonify({'status': 'reset done (no simulators connected)'})
    return jsonify({'status': 'reset broadcast'})


@app.route('/goal', methods=['POST'])
def set_goal():
    global goal_reached
    data = request.get_json() or {}
    if 'corner' in data:
        pos = corner_to_coords(str(data['corner']))
    elif 'x' in data and 'y' in data:
        pos = {"x": float(data['x']), "y": float(data['y'])}
    else:
        return jsonify({'error': 'Provide {"corner":"NE|NW|SE|SW"} OR {"x":..,"y":..}'}), 400
    goal_reached = False
    msg = {"command": "set_goal", "position": pos}
    broadcast(msg)
    return jsonify({'status': 'goal set', 'goal': pos})


@app.route('/obstacles/random', methods=['POST'])
def generate_obstacles():
    global current_obstacles
    data = request.get_json() or {}
    count = data.get('count', 8)
    obstacles = generate_random_obstacles(count)
    current_obstacles = obstacles
    msg = {"command": "set_obstacles", "obstacles": obstacles}
    broadcast(msg)
    return jsonify({'status': 'random obstacles generated', 'obstacles': obstacles})


@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        'connected_simulators': len(connected),
        'collision_count': collision_count,
        'goal_reached': goal_reached
    })


# ---------------------------
# Server Startup
# ---------------------------
def start_flask():
    print("Starting Flask server on http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)


async def main():
    global async_loop
    async_loop = asyncio.get_running_loop()
    ws_server = await websockets.serve(ws_handler, "localhost", 8080)
    print("WebSocket server started on ws://localhost:8080")
    await ws_server.wait_closed()


if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")