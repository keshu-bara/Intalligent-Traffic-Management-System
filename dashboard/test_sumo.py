import traci
import time
import numpy as np
import threading
import torch  # Add this missing import
from dqn_model import DQNAgent, EnhancedDQNAgent

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
                    reward = calculate_smart_reward(prev_state, state, current_action)
                    enhanced_agent.remember_priority(prev_state, current_action, 
                                                   reward, state, False)
                    episode_rewards.append(reward)
                
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
                    
                    print(f"🚦 Step {step}: Phase {phase} for {actual_duration}s (Action {current_action})")
                    print(f"   Traffic: N={state[0]:.2f}, S={state[3]:.2f}, E={state[6]:.2f}, W={state[9]:.2f}")
                    print(f"   Congestion: N={state[1]:.2f}, S={state[4]:.2f}, E={state[7]:.2f}, W={state[10]:.2f}")
                    
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
                
                print(f"\n📊 Step {step} Performance Summary:")
                print(f"   Average Reward (last 50): {avg_reward:.2f}")
                print(f"   Current Congestion: {current_congestion:.2f}")
                print(f"   Epsilon: {enhanced_agent.epsilon:.3f}")
                print(f"   Memory Size: {len(enhanced_agent.memory)}")
            
            time.sleep(0.05)
            
    except Exception as e:
        print(f"Enhanced simulation error: {e}")
    finally:
        traci.close()
        
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

if __name__ == "__main__":
    # Debug edges first
    debug_real_edges()
    
    # Run with proper timing constraints
    run_enhanced_dqn_simulation()
