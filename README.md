🤖 2D Robot Navigation Simulator with Q-Learning Agent
This project implements a fully integrated, real-time system for training an Autonomous Robot using the Q-Learning Reinforcement Learning (RL) algorithm. The system uses a client-server architecture to separate the visualization (browser) from the control logic (Python).
⚙️ System Overview
The entire Python component (Server and Agent) is consolidated into a single file, simplifying execution.
Component
Technology
Role
Communication
simulator.html
HTML5, Canvas, JavaScript
The Visual Interface: Renders the environment (robot, obstacles, goal). Reports collision/goal events in real-time.
WebSocket (Client)
run_robot.py
Python (Flask, WebSockets, NumPy)
The Core Brain & Hub: Contains the RL Agent, the HTTP API, and the WebSocket server, managing all communication and learning.
HTTP REST & WebSocket (Server/Client)

🚀 Getting Started (One-Step Execution)
Prerequisites
Python 3.7+
Modern web browser (for simulator.html)
Required Python packages:
pip install flask websockets asyncio numpy requests


Run Sequence
Start the Integrated Python System
This command starts the Flask API (Port 5001), the WebSocket Server (Port 8080), and begins the RL Training Agent immediately.
python run_robot.py


Open the Robot Simulator
Open simulator.html in your web browser.
The simulator will automatically connect to the Python server, and you will see the robot start its training episodes, randomly exploring the environment.
🧠 Reinforcement Learning Agent & Logging
The run_robot.py script implements Q-Learning, where the agent explores the environment and iteratively updates a lookup table (Q-table) based on rewards.
Detailed Step-by-Step Logging
The script provides verbose logging for every step, showing exactly how the learning algorithm changes the agent's "knowledge."
Log Line
Example Output
Explanation
Step Details
`[E1, S5] State: (16, 15)
Action: N
Old Q-Values
Old Q-Values: [-0.010, 0.000, -0.010, ...]
The expected future reward for all 8 actions before the learning update for the current state.
New Q-Values
New Q-Values: [-0.010, 0.000, -0.009, ...]
The expected future reward for all 8 actions after the learning update. Notice the small change in the Q-value for the action taken.
Critical Events
R: 100.0 (Goal: +100)
The robot reached the target location.

Q-Table Inspection (Every 100 Episodes)
A snapshot of the entire learned policy is printed periodically:
Log Line
Purpose
Max Q-Value: 88.5432
The highest expected future reward found anywhere in the Q-table.
Avg Q-Value: 0.1256
The average expected future reward across all possible states and actions.

⚠️ Troubleshooting
Dependencies: Confirm all required packages are installed (pip install flask websockets asyncio numpy requests).
Ports: Ensure no other process is blocking ports 5001 (HTTP) or 8080 (WS).
