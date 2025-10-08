import traci
import time
import numpy as np
import threading
import torch  # Add this missing import
from dqn_model import DQNAgent, EnhancedDQNAgent

#for dashboard
import json
import os
from datetime import datetime

#for exp32
import requests
import socket


# Add this class after your existing DashboardDataSender class
class ESP32DataSender:
    def __init__(self, esp32_ip="192.168.1.100", esp32_port=80):
        self.esp32_ip = esp32_ip
        self.esp32_port = esp32_port
        self.esp32_url = f"http://{esp32_ip}:{esp32_port}"
        
        # Traffic light state mapping for ESP32
        self.phase_to_esp32 = {
            "GGGrrrrrrrrr": {
                "direction": "North",
                "color": "GREEN",
                "led_pattern": [1, 0, 0, 0],  # North=1, South=0, East=0, West=0
                "display_code": "N_GREEN"
            },
            "rrrrrrGGGrrr": {
                "direction": "South", 
                "color": "GREEN",
                "led_pattern": [0, 1, 0, 0],
                "display_code": "S_GREEN"
            },
            "rrrGGGrrrrrr": {
                "direction": "East",
                "color": "GREEN", 
                "led_pattern": [0, 0, 1, 0],
                "display_code": "E_GREEN"
            },
            "rrrrrrrrrGGG": {
                "direction": "West",
                "color": "GREEN",
                "led_pattern": [0, 0, 0, 1],
                "display_code": "W_GREEN"
            }
        }
    
    def send_traffic_light_state(self, step, action, phase, duration, traffic_state=None):
        """Send traffic light state to ESP32"""
        try:
            # Get ESP32 format data
            esp32_data = self.phase_to_esp32.get(phase, {
                "direction": "Unknown",
                "color": "RED", 
                "led_pattern": [0, 0, 0, 0],
                "display_code": "ALL_RED"
            })
            
            # Prepare data packet for ESP32
            data_packet = {
                "timestamp": datetime.now().isoformat(),
                "simulation_step": step,
                "action": action,
                "phase_state": phase,
                "duration_seconds": duration,
                
                # ESP32 specific data
                "traffic_light": {
                    "direction": esp32_data["direction"],
                    "color": esp32_data["color"],
                    "led_pattern": esp32_data["led_pattern"],
                    "display_code": esp32_data["display_code"],
                    "duration": duration
                },
                
                # Traffic conditions (if available)
                "traffic_conditions": self._format_traffic_for_esp32(traffic_state) if traffic_state is not None else {},
                
                # Control commands
                "commands": {
                    "update_display": True,
                    "set_leds": esp32_data["led_pattern"],
                    "show_duration": duration,
                    "buzzer_alert": duration > 30  # Alert for long phases
                }
            }
            
            # Send via HTTP POST
            self._send_http_data(data_packet)
            
            # Also send via UDP for real-time updates
            self._send_udp_data(data_packet)
            
            print(f"📡 ESP32: Sent {esp32_data['direction']} {esp32_data['color']} for {duration}s")
            
        except Exception as e:
            print(f"❌ ESP32 send error: {e}")
    
    def send_traffic_metrics(self, step, state):
        """Send traffic metrics to ESP32 for display"""
        try:
            if len(state) >= 12:
                metrics_packet = {
                    "timestamp": datetime.now().isoformat(),
                    "type": "traffic_metrics",
                    "step": step,
                    
                    "metrics": {
                        "north_vehicles": int(state[0] * 10),
                        "south_vehicles": int(state[3] * 10), 
                        "east_vehicles": int(state[6] * 10),
                        "west_vehicles": int(state[9] * 10),
                        
                        "north_congestion": int(state[1] * 100),  # Percentage
                        "south_congestion": int(state[4] * 100),
                        "east_congestion": int(state[7] * 100), 
                        "west_congestion": int(state[10] * 100),
                        
                        "total_vehicles": int(sum([state[i] for i in [0, 3, 6, 9]]) * 10),
                        "avg_congestion": int(sum([state[i] for i in [1, 4, 7, 10]]) * 25)
                    },
                    
                    "display_info": {
                        "busiest_direction": ["N", "S", "E", "W"][max(range(4), key=lambda i: state[i*3])],
                        "congestion_level": "HIGH" if sum([state[i] for i in [1, 4, 7, 10]]) > 2.0 else "NORMAL"
                    }
                }
                
                self._send_http_data(metrics_packet, endpoint="/metrics")
                
        except Exception as e:
            print(f"❌ ESP32 metrics error: {e}")
    
    def send_emergency_alert(self, message, priority="HIGH"):
        """Send emergency alert to ESP32"""
        try:
            alert_packet = {
                "timestamp": datetime.now().isoformat(),
                "type": "emergency_alert",
                "message": message,
                "priority": priority,
                "commands": {
                    "flash_leds": True,
                    "buzzer_pattern": "EMERGENCY" if priority == "HIGH" else "ALERT",
                    "display_message": message[:16]  # 16 char limit for LCD
                }
            }
            
            self._send_http_data(alert_packet, endpoint="/emergency")
            self._send_udp_data(alert_packet)  # Ensure delivery
            
            print(f"🚨 ESP32: Emergency alert sent - {message}")
            
        except Exception as e:
            print(f"❌ ESP32 emergency error: {e}")
    
    def _send_http_data(self, data, endpoint="/update"):
        """Send data via HTTP POST"""
        try:
            url = f"{self.esp32_url}{endpoint}"
            response = requests.post(
                url, 
                json=data,
                timeout=2,  # Quick timeout to avoid blocking simulation
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                print(f"✅ ESP32 HTTP: Data sent successfully")
            else:
                print(f"⚠️ ESP32 HTTP: Response code {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ ESP32 HTTP error: {e}")
    
    def _send_udp_data(self, data):
        """Send data via UDP for real-time updates"""
        try:
            # Convert to compact format for UDP
            udp_data = {
                "action": data.get("action", 0),
                "duration": data.get("duration_seconds", 15),
                "leds": data.get("commands", {}).get("set_leds", [0,0,0,0]),
                "alert": data.get("commands", {}).get("buzzer_alert", False)
            }
            
            json_data = json.dumps(udp_data).encode('utf-8')
            
            # Send UDP packet
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1)
            sock.sendto(json_data, (self.esp32_ip, 8888))  # UDP port 8888
            sock.close()
            
            print(f"📡 ESP32 UDP: Quick update sent")
            
        except Exception as e:
            print(f"❌ ESP32 UDP error: {e}")
    
    def _format_traffic_for_esp32(self, state):
        """Format traffic state for ESP32 display"""
        if len(state) < 12:
            return {}
        
        return {
            "directions": {
                "N": {"vehicles": int(state[0]*10), "cong": int(state[1]*100)},
                "S": {"vehicles": int(state[3]*10), "cong": int(state[4]*100)}, 
                "E": {"vehicles": int(state[6]*10), "cong": int(state[7]*100)},
                "W": {"vehicles": int(state[9]*10), "cong": int(state[10]*100)}
            },
            "summary": {
                "total": int(sum([state[i] for i in [0,3,6,9]])*10),
                "worst": ["N","S","E","W"][max(range(4), key=lambda i: state[i*3+1])]
            }
        }
    
    def test_connection(self):
        """Test ESP32 connection"""
        try:
            test_data = {
                "type": "connection_test",
                "timestamp": datetime.now().isoformat(),
                "message": "Testing ESP32 connection from SUMO simulation"
            }
            
            response = requests.post(
                f"{self.esp32_url}/test",
                json=test_data,
                timeout=5
            )
            
            if response.status_code == 200:
                print("✅ ESP32 connection successful!")
                return True
            else:
                print(f"⚠️ ESP32 connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ ESP32 connection test failed: {e}")
            return False

# Dashboard
class DashboardDataSender:
    def __init__(self, data_dir="dashboard_data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize files
        self.files = {
            'traffic_states': os.path.join(data_dir, "traffic_states.json"),
            'performance': os.path.join(data_dir, "performance.json"),
            'phase_changes': os.path.join(data_dir, "phase_changes.json"),
            'rewards': os.path.join(data_dir, "rewards.json")
        }
        
        # Initialize with empty arrays
        for file_path in self.files.values():
            if not os.path.exists(file_path):
                with open(file_path, 'w') as f:
                    json.dump([], f)
    
    def send_traffic_state(self, step, state):
        """Send traffic state to dashboard"""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "step": step,
                "traffic_data": {
                    "north": {
                        "vehicle_count": float(state[0]) * 10,
                        "congestion_ratio": float(state[1]),
                        "avg_speed_kmh": float(state[2]) * 54
                    },
                    "south": {
                        "vehicle_count": float(state[3]) * 10,
                        "congestion_ratio": float(state[4]),
                        "avg_speed_kmh": float(state[5]) * 54
                    },
                    "east": {
                        "vehicle_count": float(state[6]) * 10,
                        "congestion_ratio": float(state[7]),
                        "avg_speed_kmh": float(state[8]) * 54
                    },
                    "west": {
                        "vehicle_count": float(state[9]) * 10,
                        "congestion_ratio": float(state[10]),
                        "avg_speed_kmh": float(state[11]) * 54
                    }
                },
                "summary": {
                    "total_vehicles": int(sum([state[i] for i in [0, 3, 6, 9]]) * 10),
                    "total_congestion": float(sum([state[i] for i in [1, 4, 7, 10]])),
                    "avg_speed": float(sum([state[i] for i in [2, 5, 8, 11]]) / 4),
                    "busiest_direction": ["North", "South", "East", "West"][max(range(4), key=lambda i: state[i*3])]
                }
            }
            self._append_to_file('traffic_states', data)
        except Exception as e:
            print(f"Error sending traffic state: {e}")
    
    def send_phase_change(self, step, action, phase, duration):
        """Send phase change to dashboard"""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "step": step,
                "action": int(action),
                "phase_state": phase,
                "duration_seconds": int(duration),
                "direction": ["North", "South", "East", "West"][action]
            }
            self._append_to_file('phase_changes', data)
        except Exception as e:
            print(f"Error sending phase change: {e}")
    
    def send_performance(self, step, avg_reward, congestion, memory_size, epsilon):
        """Send performance data to dashboard"""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "step": step,
                "metrics": {
                    "average_reward_last_50": float(avg_reward),
                    "current_congestion_level": float(congestion),
                    "dqn_memory_size": int(memory_size),
                    "exploration_rate": float(epsilon)
                }
            }
            self._append_to_file('performance', data)
        except Exception as e:
            print(f"Error sending performance: {e}")
    
    def send_rewards(self, step, action, reward_breakdown, total_reward):
        """Send reward breakdown to dashboard"""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "step": step,
                "action": int(action),
                "reward_breakdown": reward_breakdown,
                "total_reward": float(total_reward),
                "reward_analysis": {
                    "dominant_factor": max(reward_breakdown.keys(), key=lambda k: abs(reward_breakdown[k])),
                    "positive_factors": [k for k, v in reward_breakdown.items() if v > 0],
                    "negative_factors": [k for k, v in reward_breakdown.items() if v < 0]
                }
            }
            self._append_to_file('rewards', data)
        except Exception as e:
            print(f"Error sending rewards: {e}")
    
    def _append_to_file(self, file_key, data):
        """Append data to file"""
        try:
            file_path = self.files[file_key]
            
            # Read existing data
            with open(file_path, 'r') as f:
                existing_data = json.load(f)
            
            # Append new data
            existing_data.append(data)
            
            # Keep only last 200 entries
            if len(existing_data) > 200:
                existing_data = existing_data[-200:]
            
            # Write back
            with open(file_path, 'w') as f:
                json.dump(existing_data, f)
                
        except Exception as e:
            print(f"Error writing to {file_key}: {e}")


# === SUMO Setup ===
sumo_cmd = ["sumo-gui", "-c", "C:\\PC\\Projects\\SIH2\\sumo_intersection\\cfg\\csv_vehicles.sumocfg"]
traci.start(sumo_cmd)
tls_id = traci.trafficlight.getIDList()[0]

print(f"Traffic light ID: {tls_id}")
print(f"Current program: {traci.trafficlight.getProgram(tls_id)}")
print(f"Current state: {traci.trafficlight.getRedYellowGreenState(tls_id)}")

# === DQN Setup ===
# edges = ["A0", "B0", "C0", "D0"]
edges = traci.edge.getIDList()[:4]  # Update with your real edges
agent = DQNAgent(state_size=8, action_size=4)

# Enhanced DQN agent for the improved simulation
enhanced_agent = EnhancedDQNAgent(state_size=19, action_size=4)

# === Mapping actions to phases ===
action_to_phase = {
    0: "GGGrrrrrrrrr",  # North green (y > 25)
    1: "rrrrrrGGGrrr",  # South green (y < -25)
    2: "rrrGGGrrrrrr",  # East green (x > 25)
    3: "rrrrrrrrrGGG",  # West green (x < -25)
}

# Rest of your code remains the same...
def get_state():
    state = []
    for edge in edges:
        try:
            count = traci.edge.getLastStepVehicleNumber(edge)
            queue = traci.edge.getLastStepHaltingNumber(edge)
            state.extend([count, queue])
        except Exception as e:
            print(f"Error getting state for edge {edge}: {e}")
            state.extend([0, 0])  # Default values
    return np.array(state)

def get_reward():
    try:
        total_wait = sum(traci.edge.getWaitingTime(edge) for edge in edges)
        total_queue = sum(traci.edge.getLastStepHaltingNumber(edge) for edge in edges)
        return -(total_wait + total_queue)
    except Exception as e:
        print(f"Error calculating reward: {e}")
        return 0

def run_dqn_simulation():
    try:
        step = 0
        hold_timer = 0
        current_action = None
        next_action = None
        action_ready = False
        prev_state = np.array([0]*8)

        def compute_next_action():
            nonlocal next_action, action_ready
            try:
                state = get_state()
                next_action = agent.act(state)
                action_ready = True
            except Exception as e:
                print(f"Error computing action: {e}")
                next_action = 0  # Default action
                action_ready = True

        # Start first action computation
        threading.Thread(target=compute_next_action, daemon=True).start()

        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            time.sleep(0.1)
            hold_timer += 0.1
            step += 1

            # Every 3 seconds
            if hold_timer >= 3.0 and action_ready:
                try:
                    state = get_state()
                    reward = get_reward()
                    
                    if current_action is not None:
                        agent.remember(prev_state, current_action, reward, state, False)
                        agent.replay()
                    
                    current_action = next_action
                    phase = action_to_phase[current_action]
                    
                    # Apply the traffic light change
                    traci.trafficlight.setRedYellowGreenState(tls_id, phase)
                    print(f"🚦 Step {step}: Applied phase: {phase} (Action {current_action})")
                    print(f"   State: {state}")
                    print(f"   Reward: {reward}")

                    prev_state = state
                    hold_timer = 0.0
                    action_ready = False
                    threading.Thread(target=compute_next_action, daemon=True).start()
                    
                except Exception as e:
                    print(f"Error in main loop: {e}")

    except Exception as e:
        print(f"Simulation error: {e}")
    finally:
        traci.close()

# Enhanced state calculation with more traffic information
def get_enhanced_state():
    """Get comprehensive traffic state with 16 features"""
    state = []
    
    # 1. Vehicle counts and speeds for each edge
    for edge in edges:
        try:
            # Basic counts
            vehicle_count = traci.edge.getLastStepVehicleNumber(edge)
            halting_count = traci.edge.getLastStepHaltingNumber(edge)
            
            # Speed and flow information
            mean_speed = traci.edge.getLastStepMeanSpeed(edge)
            max_speed = traci.lane.getMaxSpeed(f"{edge}_0")  # Get lane max speed
            
            # Normalize values
            normalized_count = min(vehicle_count / 20.0, 1.0)  # Max 20 vehicles
            normalized_halting = min(halting_count / 15.0, 1.0)  # Max 15 halting
            normalized_speed = mean_speed / max_speed if max_speed > 0 else 0
            congestion_level = halting_count / max(vehicle_count, 1)  # Congestion ratio
            
            state.extend([normalized_count, normalized_halting, normalized_speed, congestion_level])
            
        except Exception as e:
            print(f"Error getting state for edge {edge}: {e}")
            state.extend([0, 0, 0, 0])  # 4 features per edge
    
    return np.array(state)

def get_junction_pressure():
    """Calculate pressure difference between incoming and outgoing edges"""
    try:
        # Incoming edges (vehicles approaching junction)
        incoming_pressure = 0
        outgoing_pressure = 0
        
        for edge in edges:
            vehicle_count = traci.edge.getLastStepVehicleNumber(edge)
            # Assume first 2 edges are incoming, last 2 are outgoing
            if edges.index(edge) < 2:
                incoming_pressure += vehicle_count
            else:
                outgoing_pressure += vehicle_count
        
        return incoming_pressure - outgoing_pressure
    except:
        return 0

def get_comprehensive_state():
    """Get complete traffic state with temporal and spatial information"""
    # Basic enhanced state (16 features)
    basic_state = get_enhanced_state()
    
    # Additional features
    try:
        # Junction pressure
        pressure = get_junction_pressure()
        
        # Current traffic light info
        current_phase_duration = traci.trafficlight.getPhaseDuration(tls_id)
        current_phase_index = traci.trafficlight.getPhase(tls_id)
        phase_elapsed = traci.trafficlight.getNextSwitch(tls_id) - traci.simulation.getTime()
        
        # Emergency or priority vehicle detection
        emergency_vehicles = 0
        for veh_id in traci.vehicle.getIDList():
            if 'emergency' in veh_id.lower() or 'bus' in veh_id.lower():
                emergency_vehicles += 1
        
        # Normalize additional features
        normalized_pressure = max(-1.0, min(1.0, pressure / 10.0))
        normalized_phase_elapsed = phase_elapsed / 30.0  # Assuming max 30s phases
        normalized_emergency = min(emergency_vehicles / 5.0, 1.0)
        
        additional_features = [normalized_pressure, normalized_phase_elapsed, normalized_emergency]
        
        return np.concatenate([basic_state, additional_features])
        
    except Exception as e:
        print(f"Error in comprehensive state: {e}")
        return basic_state

def calculate_comprehensive_reward(prev_state, current_state, action, phase_duration):
    """Calculate reward based on multiple traffic optimization criteria"""
    
    # 1. Throughput reward (vehicles that completed their journey)
    throughput_reward = 0
    try:
        current_vehicles = set(traci.vehicle.getIDList())
        if hasattr(calculate_comprehensive_reward, 'prev_vehicles'):
            completed_vehicles = calculate_comprehensive_reward.prev_vehicles - current_vehicles
            throughput_reward = len(completed_vehicles) * 2.0  # Reward for completed trips
        calculate_comprehensive_reward.prev_vehicles = current_vehicles
    except:
        pass
    
    # 2. Congestion reduction reward
    congestion_reward = 0
    try:
        total_halting_prev = sum(prev_state[i] for i in range(1, 16, 4))  # Halting vehicles
        total_halting_curr = sum(current_state[i] for i in range(1, 16, 4))
        
        if total_halting_curr < total_halting_prev:
            congestion_reward = (total_halting_prev - total_halting_curr) * 3.0
        else:
            congestion_reward = (total_halting_prev - total_halting_curr) * 1.0
    except:
        pass
    
    # 3. Speed optimization reward
    speed_reward = 0
    try:
        avg_speed_curr = sum(current_state[i] for i in range(2, 16, 4)) / 4  # Average normalized speed
        speed_reward = avg_speed_curr * 2.0  # Reward higher speeds
    except:
        pass
    
    # 4. Phase duration efficiency reward
    efficiency_reward = 0
    if 5 <= phase_duration <= 45:  # Reward reasonable phase durations
        efficiency_reward = 1.0
    else:
        efficiency_reward = -0.5  # Penalize too short or too long phases
    
    # 5. Emergency vehicle priority reward
    emergency_reward = 0
    try:
        if len(current_state) > 18:  # Has emergency vehicle info
            emergency_count = current_state[18]
            if emergency_count > 0 and action == get_emergency_priority_action():
                emergency_reward = 5.0  # High reward for emergency priority
    except:
        pass
    
    # 6. Queue length penalty
    queue_penalty = -sum(current_state[i] for i in range(1, 16, 4)) * 0.5
    
    total_reward = (throughput_reward + congestion_reward + speed_reward + 
                   efficiency_reward + emergency_reward + queue_penalty)
    
    return total_reward

def get_emergency_priority_action():
    """Determine action for emergency vehicle priority"""
    # Simple implementation - find direction with emergency vehicles
    for i, edge in enumerate(edges):
        try:
            vehicles_on_edge = traci.edge.getLastStepVehicleIDs(edge)
            for veh_id in vehicles_on_edge:
                if 'emergency' in veh_id.lower() or 'bus' in veh_id.lower():
                    return i  # Return action corresponding to this direction
        except:
            continue
    return 

def run_enhanced_dqn_simulation():
    """Enhanced DQN simulation with proper minimum timing constraints"""
    
    enhanced_agent = EnhancedDQNAgent(state_size=12, action_size=4)  # Use position-based state
    
    #Intializing dashboard sender
    dashboard = DashboardDataSender()
    esp32 = ESP32DataSender(esp32_ip="192.168.191.87")

    esp32_connected = esp32.test_connection()
    if not esp32_connected:
        print("⚠️ ESP32 not connected. Continuing without Hardware integration.")

    try:
        step = 0
        current_phase_start = 0
        current_action = None
        current_duration = 15
        prev_state = None
        
        # Timing constraints
        MINIMUM_GREEN_TIME = 10  # Minimum 10 seconds per direction
        MAXIMUM_GREEN_TIME = 45  # Maximum 45 seconds per direction
        DEFAULT_GREEN_TIME = 15  # Default when no traffic
        
        # Performance tracking
        episode_rewards = []
        congestion_levels = []
        
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            current_time = traci.simulation.getTime()
            step += 1
            
            # Get current state using position-based detection
            state = get_correct_traffic_state()

            if step % 10 == 0:
                dashboard.send_traffic_state(step, state)

                if step % 20 == 0 and esp32_connected:
                    esp32.send_traffic_metrics(step, state)
            
            # Check if current phase should end
            phase_elapsed = current_time - current_phase_start
            
            # Enhanced phase change logic with minimum timing
            should_change_phase = (
                current_action is None or  # First phase
                (phase_elapsed >= MINIMUM_GREEN_TIME and  # Minimum time passed
                 (phase_elapsed >= current_duration or    # Planned duration reached
                  phase_elapsed >= MAXIMUM_GREEN_TIME))   # Maximum time reached
            )
            
            if should_change_phase:
                # Calculate reward for previous action
                if prev_state is not None and current_action is not None:
                    reward , reward_breakdown  = calculate_smart_reward_with_breakdown(prev_state, state, current_action)

                    enhanced_agent.remember_priority(prev_state, current_action, 
                                                   reward, state, False)
                    episode_rewards.append(reward)

                    dashboard.send_rewards(step, current_action, reward_breakdown, reward)
                
                # Choose new action with traffic-aware logic
                current_action, current_duration = choose_intelligent_action_and_duration(
                    enhanced_agent, state, MINIMUM_GREEN_TIME, MAXIMUM_GREEN_TIME, DEFAULT_GREEN_TIME
                )
                
                # Apply traffic light change with validation
                phase = apply_intelligent_action(current_action, state)
                
                try:
                    traci.trafficlight.setRedYellowGreenState(tls_id, phase)
                    # Ensure minimum duration is respected
                    actual_duration = max(current_duration, MINIMUM_GREEN_TIME)
                    traci.trafficlight.setPhaseDuration(tls_id, int(actual_duration))


                    
                    # print(f"🚦 Step {step}: Phase {phase} for {actual_duration}s (Action {current_action})")
                    # print(f"   Traffic: N={state[0]:.2f}, S={state[3]:.2f}, E={state[6]:.2f}, W={state[9]:.2f}")
                    # print(f"   Congestion: N={state[1]:.2f}, S={state[4]:.2f}, E={state[7]:.2f}, W={state[10]:.2f}")
                    dashboard.send_phase_change(step, current_action, phase, actual_duration)

                    if esp32_connected:
                        esp32.send_traffic_light_state(step, current_action, phase, actual_duration, traffic_state=state)

                    total_congestion = sum([state[i] for i in [1, 4, 7, 10]])

                    if total_congestion > 3.0 and esp32_connected:
                        esp32.send_emergency_alert("HIGH CONGESTION", priority="HIGH")
                    
                    if len(episode_rewards) > 0:
                        print(f"   Recent reward: {episode_rewards[-1]:.2f}")
                    
                except Exception as e:
                    print(f"Error applying phase: {e}")
                
                current_phase_start = current_time
                current_duration = actual_duration  # Update with actual duration
                prev_state = state.copy()
                
                # Train the model
                if len(enhanced_agent.memory) > 100:
                    enhanced_agent.enhanced_replay(batch_size=64)
            
            # Track performance every 100 steps
            if step % 100 == 0:

                avg_reward = np.mean(episode_rewards[-50:]) if episode_rewards else 0
                current_congestion = sum(state[1::4]) if len(state) > 4 else 0
                congestion_levels.append(current_congestion)

                
                # print(f"\n📊 Step {step} Performance Summary:")
                # print(f"   Average Reward (last 50): {avg_reward:.2f}")
                # print(f"   Current Congestion: {current_congestion:.2f}")
                # print(f"   Epsilon: {enhanced_agent.epsilon:.3f}")
                # print(f"   Memory Size: {len(enhanced_agent.memory)}")

                dashboard.send_performance(step, avg_reward, current_congestion, len(enhanced_agent.memory), enhanced_agent.epsilon)
            
            time.sleep(0.05)
            
    except Exception as e:
        print(f"Enhanced simulation error: {e}")
    finally:
        traci.close()
        # try:
            
        #     final_summary = {
        #         "timestamp": datetime.now().isoformat(),
        #         "simulation_completed": True,
        #         "total_steps": step,
        #         "final_metrics": {
        #             "total_rewards": len(episode_rewards),
        #             "avg_reward": float(np.mean(episode_rewards) if episode_rewards else 0),
        #             "final_congestion": float(congestion_levels[-1] if congestion_levels else 0),
        #             "model_saved": True
        #         }
        #     }

        #     requests.post(f"{API_BASE_URL}/simulation/complete", json=final_summary, timeout=5)
        #     print("✅ Final summary sent to API")
        # except:
        #     pass
        if esp32_connected:
            esp32.send_emergency_alert("SIMULATION ENDED", priority="LOW")
        
        try:
            torch.save(enhanced_agent.model.state_dict(), 'enhanced_traffic_dqn.pth')
            print("Model saved successfully!")



        except Exception as e:
            print(f"Error saving model: {e}")

def get_correct_traffic_state():
    """Get traffic state using vehicle positions instead of unreliable edge data"""
    try:
        vehicles = traci.vehicle.getIDList()
        
        # Direction counters based on vehicle positions
        north_bound = 0  # Vehicles going north (y > 0, moving up)
        south_bound = 0  # Vehicles going south (y < 0, moving down)  
        east_bound = 0   # Vehicles going east (x > 0, moving right)
        west_bound = 0   # Vehicles going west (x < 0, moving left)
        
        # Speed counters for congestion detection
        north_speeds = []
        south_speeds = []
        east_speeds = []
        west_speeds = []
        
        for veh_id in vehicles:
            try:
                pos = traci.vehicle.getPosition(veh_id)
                speed = traci.vehicle.getSpeed(veh_id)
                x, y = pos[0], pos[1]
                
                # Categorize by position and direction
                if y > 25:  # North area
                    north_bound += 1
                    north_speeds.append(speed)
                elif y < -25:  # South area  
                    south_bound += 1
                    south_speeds.append(speed)
                elif x > 25:  # East area
                    east_bound += 1
                    east_speeds.append(speed)
                elif x < -25:  # West area
                    west_bound += 1
                    west_speeds.append(speed)
                    
            except:
                continue
        
        # Calculate congestion (vehicles with speed < 2 m/s)
        def get_congestion(speeds):
            if not speeds:
                return 0
            return len([s for s in speeds if s < 2.0]) / len(speeds)
        
        # Create state vector
        state = [
            min(north_bound / 10.0, 1.0),    # Normalized vehicle count
            get_congestion(north_speeds),     # Congestion ratio
            np.mean(north_speeds) / 15.0 if north_speeds else 0,  # Normalized avg speed
            
            min(south_bound / 10.0, 1.0),
            get_congestion(south_speeds),
            np.mean(south_speeds) / 15.0 if south_speeds else 0,
            
            min(east_bound / 10.0, 1.0),
            get_congestion(east_speeds),
            np.mean(east_speeds) / 15.0 if east_speeds else 0,
            
            min(west_bound / 10.0, 1.0),
            get_congestion(west_speeds),
            np.mean(west_speeds) / 15.0 if west_speeds else 0,
        ]
        
        print(f"🚦 Traffic state: N={north_bound}, S={south_bound}, E={east_bound}, W={west_bound}")
        
        return np.array(state)
        
    except Exception as e:
        print(f"Error in traffic state: {e}")
        return np.zeros(12)

def apply_intelligent_action(action, state):
    """Apply action only if it makes sense"""
    # state format: [N_count, N_cong, N_speed, S_count, S_cong, S_speed, E_count, E_cong, E_speed, W_count, W_cong, W_speed]
    
    direction_traffic = [
        state[0],   # North traffic
        state[3],   # South traffic  
        state[6],   # East traffic
        state[9],   # West traffic
    ]
    
    direction_congestion = [
        state[1],   # North congestion
        state[4],   # South congestion
        state[7],   # East congestion
        state[10],  # West congestion
    ]
    
    # Only apply action if the direction has significant traffic or congestion
    if direction_traffic[action] > 0.1 or direction_congestion[action] > 0.2:
        phase = action_to_phase[action]
        print(f"✅ Applying action {action}: Traffic={direction_traffic[action]:.2f}, Congestion={direction_congestion[action]:.2f}")
        return phase
    else:
        # Find direction with most traffic
        max_traffic_dir = np.argmax(direction_traffic)
        if direction_traffic[max_traffic_dir] > 0.05:  # Has some traffic
            phase = action_to_phase[max_traffic_dir]
            print(f"🔄 Override: Action {action} → {max_traffic_dir} (more traffic)")
            return phase
        else:
            # Default rotation if no traffic
            phase = action_to_phase[action]
            print(f"🔀 Default rotation: Action {action}")
            return phase
            
# Add this debug function to find your real edges:
def debug_real_edges():
    """Find the actual edge names in your SUMO network"""
    try:
        all_edges = traci.edge.getIDList()
        print(f"🔍 All edges in network: {all_edges}")
        
        # Check which edges have vehicles
        edges_with_traffic = []
        for edge in all_edges:
            try:
                count = traci.edge.getLastStepVehicleNumber(edge)
                if count > 0:
                    edges_with_traffic.append((edge, count))
            except:
                pass
        
        print(f"🚗 Edges with traffic: {edges_with_traffic}")
        
        # Check edge positions to understand directions
        for edge in all_edges[:8]:  # Check first 8 edges
            try:
                shape = traci.edge.getShape(edge)
                print(f"📍 Edge {edge}: shape = {shape}")
            except:
                pass
                
    except Exception as e:
        print(f"Debug error: {e}")

# Run this before your main simulation:
debug_real_edges()


def choose_intelligent_action_and_duration(agent, state, min_time, max_time, default_time):
    """Choose action and duration based on traffic conditions with minimum timing"""
    
    # Extract traffic information per direction
    direction_traffic = [state[0], state[3], state[6], state[9]]  # N, S, E, W vehicle counts
    direction_congestion = [state[1], state[4], state[7], state[10]]  # N, S, E, W congestion
    direction_speeds = [state[2], state[5], state[8], state[11]]  # N, S, E, W speeds
    
    # Let DQN choose the action
    dqn_action = agent.act(state)
    
    # Validate and potentially override the action
    chosen_action = validate_action_choice(dqn_action, direction_traffic, direction_congestion)
    
    # Calculate duration based on traffic conditions
    duration = calculate_adaptive_duration(
        chosen_action, direction_traffic, direction_congestion, direction_speeds, 
        min_time, max_time, default_time
    )
    
    return chosen_action, duration

def validate_action_choice(dqn_action, traffic, congestion):
    """Validate DQN action choice and override if necessary"""
    
    # Check if chosen direction has significant traffic or congestion
    chosen_traffic = traffic[dqn_action]
    chosen_congestion = congestion[dqn_action]
    
    # If chosen direction has reasonable traffic/congestion, use it
    if chosen_traffic > 0.05 or chosen_congestion > 0.1:
        print(f"✅ DQN action {dqn_action} validated: Traffic={chosen_traffic:.2f}, Congestion={chosen_congestion:.2f}")
        return dqn_action
    
    # Otherwise, find the direction with most traffic
    max_traffic_idx = np.argmax(traffic)
    max_congestion_idx = np.argmax(congestion)
    
    # Choose direction with highest traffic or congestion
    if traffic[max_traffic_idx] > 0.05:
        print(f"🔄 Override: DQN chose {dqn_action} → {max_traffic_idx} (higher traffic: {traffic[max_traffic_idx]:.2f})")
        return max_traffic_idx
    elif congestion[max_congestion_idx] > 0.1:
        print(f"🔄 Override: DQN chose {dqn_action} → {max_congestion_idx} (higher congestion: {congestion[max_congestion_idx]:.2f})")
        return max_congestion_idx
    else:
        # No significant traffic anywhere, use round-robin or DQN choice
        print(f"🔀 No significant traffic, using DQN choice: {dqn_action}")
        return dqn_action

def calculate_adaptive_duration(action, traffic, congestion, speeds, min_time, max_time, default_time):
    """Calculate adaptive phase duration based on traffic conditions"""
    
    # Get traffic metrics for chosen direction
    direction_traffic = traffic[action]
    direction_congestion = congestion[action]
    direction_speed = speeds[action]
    
    # Base duration calculation
    if direction_traffic > 0.7 or direction_congestion > 0.6:
        # High traffic or congestion - longer green
        base_duration = max_time  # 45 seconds
        reason = "high traffic/congestion"
    elif direction_traffic > 0.3 or direction_congestion > 0.3:
        # Medium traffic - medium duration
        base_duration = (min_time + max_time) // 2  # ~27 seconds
        reason = "medium traffic"
    elif direction_traffic > 0.05:
        # Low but some traffic - default duration  
        base_duration = default_time  # 15 seconds
        reason = "low traffic"
    else:
        # No traffic - minimum duration
        base_duration = min_time  # 10 seconds
        reason = "no traffic"
    
    # Adjust based on speed (if vehicles are moving well, shorter green needed)
    if direction_speed > 0.7:  # High speed, good flow
        base_duration = max(min_time, int(base_duration * 0.8))
        reason += ", good flow"
    elif direction_speed < 0.3 and direction_traffic > 0.1:  # Low speed with traffic
        base_duration = min(max_time, int(base_duration * 1.2))
        reason += ", slow flow"
    
    # Ensure bounds
    final_duration = max(min_time, min(base_duration, max_time))
    
    print(f"⏱️  Duration calculation: {final_duration}s ({reason})")
    return final_duration

def calculate_smart_reward(prev_state, current_state, action):
    """Calculate reward that considers timing efficiency"""
    
    # Extract direction metrics
    prev_traffic = [prev_state[i] for i in [0, 3, 6, 9]]  # N, S, E, W counts
    curr_traffic = [current_state[i] for i in [0, 3, 6, 9]]
    
    prev_congestion = [prev_state[i] for i in [1, 4, 7, 10]]  # N, S, E, W congestion
    curr_congestion = [current_state[i] for i in [1, 4, 7, 10]]
    
    curr_speeds = [current_state[i] for i in [2, 5, 8, 11]]  # N, S, E, W speeds
    
    # 1. Traffic clearance reward (vehicles that moved through)
    total_prev_traffic = sum(prev_traffic)
    total_curr_traffic = sum(curr_traffic)
    clearance_reward = (total_prev_traffic - total_curr_traffic) * 5.0
    
    # 2. Congestion reduction reward
    total_prev_congestion = sum(prev_congestion)
    total_curr_congestion = sum(curr_congestion)
    congestion_reward = (total_prev_congestion - total_curr_congestion) * 3.0
    
    # 3. Action efficiency reward (did we give green to the right direction?)
    chosen_direction_traffic = curr_traffic[action]
    chosen_direction_congestion = curr_congestion[action]
    
    if chosen_direction_traffic > 0.1 or chosen_direction_congestion > 0.2:
        efficiency_reward = 2.0  # Good choice
    elif chosen_direction_traffic > 0.05:
        efficiency_reward = 1.0  # Okay choice
    else:
        efficiency_reward = -1.0  # Poor choice (no traffic in that direction)
    
    # 4. Speed reward (higher speeds = better flow)
    avg_speed = np.mean(curr_speeds)
    speed_reward = avg_speed * 2.0
    
    # 5. Penalty for excessive congestion
    congestion_penalty = -sum(curr_congestion) * 2.0
    
    total_reward = (clearance_reward + congestion_reward + efficiency_reward + 
                   speed_reward + congestion_penalty)
    
    print(f"💰 Reward: Clear={clearance_reward:.1f}, Cong={congestion_reward:.1f}, "
          f"Eff={efficiency_reward:.1f}, Speed={speed_reward:.1f}, Total={total_reward:.1f}")
    
    return total_reward

def calculate_smart_reward_with_breakdown(prev_state, current_state, action):
    """Calculate reward with detailed breakdown for dashboard"""
    
    # Extract direction metrics
    prev_traffic = [prev_state[i] for i in [0, 3, 6, 9]]
    curr_traffic = [current_state[i] for i in [0, 3, 6, 9]]
    
    prev_congestion = [prev_state[i] for i in [1, 4, 7, 10]]
    curr_congestion = [current_state[i] for i in [1, 4, 7, 10]]
    
    curr_speeds = [current_state[i] for i in [2, 5, 8, 11]]
    
    # Calculate components
    clearance_reward = (sum(prev_traffic) - sum(curr_traffic)) * 5.0
    congestion_reward = (sum(prev_congestion) - sum(curr_congestion)) * 3.0
    
    chosen_direction_traffic = curr_traffic[action]
    chosen_direction_congestion = curr_congestion[action]
    
    if chosen_direction_traffic > 0.1 or chosen_direction_congestion > 0.2:
        efficiency_reward = 2.0
    elif chosen_direction_traffic > 0.05:
        efficiency_reward = 1.0
    else:
        efficiency_reward = -1.0
    
    speed_reward = np.mean(curr_speeds) * 2.0
    congestion_penalty = -sum(curr_congestion) * 2.0
    
    total_reward = (clearance_reward + congestion_reward + efficiency_reward + 
                   speed_reward + congestion_penalty)
    
    # Breakdown for dashboard
    reward_breakdown = {
        "clearance_reward": float(clearance_reward),
        "congestion_reward": float(congestion_reward),
        "efficiency_reward": float(efficiency_reward),
        "speed_reward": float(speed_reward),
        "congestion_penalty": float(congestion_penalty)
    }
    
    return total_reward, reward_breakdown
if __name__ == "__main__":
    # Debug edges first
    debug_real_edges()
    
    # Run with proper timing constraints
    run_enhanced_dqn_simulation()
