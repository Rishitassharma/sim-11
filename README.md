Here’s a **concise but complete README.md** including a section on saving and using training data after model training:

---

# 🦾 2D Robot Simulator

A **real-time 2D robot simulation** with WebSocket control and collision detection.
Train your navigation algorithm, save the learned data, and test it in the simulator.

---

## ⚡ Features

* Live **WebSocket** robot control with collision & goal detection
* HTML5 Canvas frontend (`simulator.html`)
* Simple **Flask + websockets** backend
* Supports **saving & reusing training data** for testing

---

## 🏗 Project Structure

```
server.py         # Flask + WebSocket backend
simulator.html    # Frontend UI & 2D canvas
requirements.txt  # Python dependencies
```

---

## 🚀 Quick Start

```bash
git clone https://github.com/<your-username>/2d-robot-simulator.git
cd 2d-robot-simulator
pip install -r requirements.txt
python server.py
```

Open **simulator.html** in your browser; it connects to `ws://localhost:8080`.

---

## 🕹 WebSocket Commands

| Command         | Example                                                                 |
| --------------- | ----------------------------------------------------------------------- |
| `move`          | `{"command":"move","target":{"x":400,"y":200}}`                         |
| `move_relative` | `{"command":"move_relative","angle":90,"distance":100}`                 |
| `stop`          | `{"command":"stop"}`                                                    |
| `set_goal`      | `{"command":"set_goal","position":{"x":350,"y":50}}`                    |
| `set_obstacles` | `{"command":"set_obstacles","obstacles":[{"x":150,"y":120,"size":25}]}` |
| `reset`         | `{"command":"reset"}`                                                   |

---

## 💾 Saving & Using Training Data

When your training loop in `server.py` (or your own training script) completes:

```python
import numpy as np

# After training
np.save('training_data.npy', training_data)

# Later, for testing
loaded = np.load('training_data.npy', allow_pickle=True)
# Use `loaded` in your testing routine or to replay actions
```

This allows you to **save learned policies, robot paths, or sensor data** and reload them for evaluation without retraining.

---

## 🛠 Dependencies

```
flask
websockets
numpy
requests
```

---

## 📜 License

MIT – free to use and modify.

---

*Train ➜ Save ➜ Reload ➜ Test — all in a clean 2D simulator.*

