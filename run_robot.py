import asyncio
import json
import websockets
from flask import Flask, request, jsonify
import threading
import random
import requests
import time
import numpy as np
import sys

# --- 0. FLASK APP INITIALIZATION ---
app = Flask(__name__)


# Enable CORS for the simulator.html
@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


# ---------------------------
# GLOBAL STATE (Server Component)
# ---------------------------
connected = set()
async_loop = None
collision_count = 0
goal_reached = False
current_obstacles = []
CANVAS_WIDTH = 650
CANVAS_HEIGHT = 600
robot_state = {'x': 320, 'y': 300, 'angle': 0}

# ---------------------------
# CONFIGURATION (RL Agent Component)
# ---------------------------
FLASK_API_URL = "http://localhost:5001"
# RL Parameters
LEARNING_RATE = 0.1
DISCOUNT_FACTOR = 0.95
EPISODES = 2000
MAX_STEPS_PER_EPISODE = 100
EPSILON_START = 1.0
EPSILON_END = 0.01
EPSILON_DECAY = 0.995

# Discretization
GRID_SIZE = 20
GRID_WIDTH = int(CANVAS_WIDTH / GRID_SIZE)
GRID_HEIGHT = int(CANVAS_HEIGHT / GRID_SIZE)


# ---------------------------
# SERVER UTILITIES (From server.py)
# ---------------------------

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


def broadcast(msg: dict):
    # This function is now called from the training thread (non-async)
    if not connected: return False
    for ws in list(connected):
        try:
            # Safely push the async coroutine to the running event loop
            asyncio.run_coroutine_threadsafe(ws.send(json.dumps(msg)), async_loop)
        except Exception as e:
            # print(f"Error broadcasting: {e}")
            pass
    return True


# ---------------------------
# WebSocket Handler (From server.py)
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
                    # Update robot state from the simulator (source of truth)
                    robot_pos = data.get("robot_position")
                    if robot_pos and 'x' in robot_pos and 'y' in robot_pos:
                        robot_state['x'] = robot_pos['x']
                        robot_state['y'] = robot_pos['y']

                    if data.get("type") == "collision" and data.get("collision"):
                        collision_count += 1
                        # print(f"Collision detected! Total: {collision_count}")
                    elif data.get("type") == "goal_reached":
                        goal_reached = True
                        # print(f"Goal reached at: {data.get('robot_position')}")
            except Exception:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected.remove(websocket)


# ---------------------------
# FLASK API ENDPOINTS (From server.py)
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
# API UTILITIES (From run_robot.py)
# ---------------------------
def post_api(endpoint, data=None):
    try:
        res = requests.post(f"{FLASK_API_URL}/{endpoint}", json=data, timeout=3)
        res.raise_for_status()
        return res.json()
    except requests.RequestException:
        return None


def get_api(endpoint):
    try:
        res = requests.get(f"{FLASK_API_URL}/{endpoint}", timeout=3)
        res.raise_for_status()
        return res.json()
    except requests.RequestException:
        return None


# ---------------------------
# RL AGENT CLASS (From run_robot.py)
# ---------------------------
class RLAgent:
    def __init__(self):
        self.q_table = np.zeros((GRID_WIDTH, GRID_HEIGHT, 8))
        self.epsilon = EPSILON_START
        self.actions = [
            (0, -GRID_SIZE), (GRID_SIZE, 0), (0, GRID_SIZE), (-GRID_SIZE, 0),
            (GRID_SIZE, -GRID_SIZE), (GRID_SIZE, GRID_SIZE), (-GRID_SIZE, GRID_SIZE), (-GRID_SIZE, -GRID_SIZE)
        ]

    def discretize_state(self, x, y):
        grid_x = int(x / GRID_SIZE)
        grid_y = int(y / GRID_SIZE)
        return max(0, min(grid_x, GRID_WIDTH - 1)), max(0, min(grid_y, GRID_HEIGHT - 1))

    def choose_action(self, state):
        if random.uniform(0, 1) < self.epsilon:
            return random.randint(0, 7)
        else:
            return np.argmax(self.q_table[state])

    def update_q_table(self, state, action, reward, next_state):
        old_value = self.q_table[state][action]
        next_max = np.max(self.q_table[next_state])
        new_value = old_value + LEARNING_RATE * (reward + DISCOUNT_FACTOR * next_max - old_value)
        self.q_table[state][action] = new_value

    def decay_epsilon(self):
        if self.epsilon > EPSILON_END:
            self.epsilon *= EPSILON_DECAY


# ---------------------------
# RL AGENT MAIN TRAINING LOOP (From run_robot.py)
# ---------------------------
def run_training_agent():
    # Set global options for NumPy printing to make the Q-table output readable
    np.set_printoptions(precision=4, suppress=True, linewidth=150)

    action_names = ['N', 'E', 'S', 'W', 'NE', 'SE', 'SW', 'NW']

    print("--- 🤖 Initializing RL Training Agent ---")
    # Wait briefly for the server threads to start
    time.sleep(2)

    agent = RLAgent()

    # Check connectivity before starting
    try:
        res = requests.get(FLASK_API_URL + '/status', timeout=1)
        if res.status_code != 200:
            print(f"Error: Flask server not reachable at {FLASK_API_URL}. Cannot start training.")
            return
    except requests.exceptions.ConnectionError:
        print(f"Error: Connection to Flask server at {FLASK_API_URL} failed. Cannot start training.")
        return

    print("--- ✅ Server OK. Starting RL Training ---")
    for episode in range(EPISODES):
        # 1. Reset Environment and Set Goal
        post_api("reset")
        post_api("goal", {"corner": "NE"})
        post_api("obstacles/random", {"count": 10})
        time.sleep(0.1)

        initial_state_data = get_api("robot/state")
        if not initial_state_data:
            print("Could not retrieve initial state. Aborting.")
            return

        state_coords = (initial_state_data['x'], initial_state_data['y'])
        state = agent.discretize_state(*state_coords)

        total_reward = 0
        done = False
        last_collision_count = 0

        # --- Q-Value Inspection (Every 100 Episodes) ---
        if (episode + 1) % 100 == 0:
            max_q = np.max(agent.q_table)
            avg_q = np.mean(agent.q_table)
            print(f"\n--- 📈 Q-TABLE INSPECTION (EPISODE {episode + 1}) ---")
            print(f"Max Q-Value: {max_q:.4f} | Avg Q-Value: {avg_q:.4f}")
            print("-------------------------------------------------")
        # ---------------------------------------------

        for step in range(MAX_STEPS_PER_EPISODE):
            # Record Q-values before the action is chosen
            old_q_values = agent.q_table[state].copy()

            action_index = agent.choose_action(state)
            dx, dy = agent.actions[action_index]

            new_x = max(0, min(CANVAS_WIDTH - 1, state_coords[0] + dx))
            new_y = max(0, min(CANVAS_HEIGHT - 1, state_coords[1] + dy))

            # 2. Command Move
            post_api("move", {"x": new_x, "y": new_y})
            time.sleep(0.1)

            # 3. Get Status and Next State
            status = get_api("status")
            new_state_data = get_api("robot/state")

            if not status or not new_state_data:
                # Log only on failure
                print("Lost connection to server.")
                break

            new_state_coords = (new_state_data['x'], new_state_data['y'])
            next_state = agent.discretize_state(*new_state_coords)
            reward = -1  # Step penalty

            event_tag = ""

            if status.get('goal_reached'):
                reward = 100
                done = True
                event_tag = " (Goal: +100)"

            current_collision_count = status.get('collision_count', 0)
            if current_collision_count > last_collision_count:
                reward = -100
                done = True
                event_tag = " (Collision: -100)"
            last_collision_count = current_collision_count

            # 4. Update Q-Table (Learning step)
            agent.update_q_table(state, action_index, reward, next_state)

            # --- DETAILED STEP-BY-STEP Q-VALUE LOG ---
            new_q_values = agent.q_table[state]

            print(
                f"\n[E{episode + 1}, S{step + 1}] State: {state} | Action: {action_names[action_index]} | R: {reward:.1f}{event_tag} | Epsilon: {agent.epsilon:.4f}")
            print(f"  Old Q-Values: {old_q_values}")
            print(f"  New Q-Values: {new_q_values}")
            # -----------------------------------------

            state, state_coords = next_state, new_state_coords
            total_reward += reward

            if done:
                break

        agent.decay_epsilon()
        # Summary Log (Current Episode, Steps, Total Reward, Epsilon)
        print(
            f"\n--- Episode {episode + 1}/{EPISODES} Summary --- Steps: {step + 1}, Total Reward: {total_reward:.1f}, Epsilon: {agent.epsilon:.4f}")
        sys.stdout.flush()  # Force print output

    print("\n--- ✅ Training Finished ---")
    np.save("q_table.npy", agent.q_table)
    print("Q-table saved to q_table.npy!")


# ---------------------------
# MAIN ENTRY POINT
# ---------------------------
def start_flask():
    # Flask server is started in a separate thread
    print("Starting Flask server (HTTP API) on http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)


async def start_websocket():
    global async_loop
    async_loop = asyncio.get_running_loop()
    ws_server = await websockets.serve(ws_handler, "localhost", 8080)
    print("WebSocket server started on ws://localhost:8080")
    await ws_server.wait_closed()


if __name__ == "__main__":
    # 1. Start Flask (HTTP API) in a separate thread
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()


    # 2. Start WebSocket (Real-time communication) in a separate thread
    # We use a standard thread to run the asyncio loop for the websocket server
    def start_ws_in_thread():
        try:
            asyncio.run(start_websocket())
        except Exception as e:
            print(f"WebSocket service failed: {e}")


    ws_thread = threading.Thread(target=start_ws_in_thread, daemon=True)
    ws_thread.start()

    # 3. Start the RL Agent Training Loop in the main thread
    # The main thread blocks here until training is done
    try:
        run_training_agent()
    except KeyboardInterrupt:
        print("\nTraining interrupted.")
    except Exception as e:
        print(f"\nAn error occurred during training: {e}")

    print("Application shutdown complete.")
