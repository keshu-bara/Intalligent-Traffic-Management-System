# FastAPI server to connect SUMO simulation with web dashboard
from fastapi import FastAPI , Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import traci
import threading
import time
import uvicorn
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel
from typing import Dict, List
import json
from datetime import datetime

# Add missing global variables
traffic_light_manual_mode = False
manual_traffic_states = {}
traffic_statistics = {
    "total_vehicles_passed": 0,
    "total_simulation_time": 0,
    "congestion_events": [],
    "vehicle_history": [],
    "peak_vehicle_count": 0,
    "average_speed_history": []
}

# Add missing Pydantic model classes
class TrafficLightControl(BaseModel):
    direction: str  # north, south, east, west
    state: str     # red, green, yellow

class TrafficLightMode(BaseModel):
    manual_mode: bool

class ConfigSelect(BaseModel):
    config_name: str

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


config_files = [f for f in os.listdir(os.path.join(PARENT_DIR, "sumo_intersection", "cfg")) if f.endswith(".sumocfg")]

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")



# Global variables for SUMO connection
sumo_running = False
simulation_data = {"vehicles": [], "step": 0}
config_file = "csv_vehicles.sumocfg"

simulation_files_path = os.path.join(PARENT_DIR, "sumo_intersection", "cfg")

simu_files = [f for f in os.listdir(simulation_files_path) if f.endswith(".sumocfg")]
def cleanup_sumo():
    """Ensure SUMO is closed on exit"""
    global sumo_running
    sumo_running = False  # Set this first
    try:
        # Check if TraCI is connected
        if 'traci' in globals():
            try:
                # Try to get simulation step to test connection
                traci.simulation.getTime()
                traci.close()
                print("TraCI connection closed properly")
            except:
                pass
    except:
        pass

    try:
        os.system("taskkill /f /im sumo-gui.exe >nul 2>&1")
        os.system("taskkill /f /im sumo.exe >nul 2>&1")
    except:
        pass

def start_sumo():
    """Enhanced SUMO simulation with manual control and statistics"""
    global sumo_running, config_file, traffic_statistics, manual_traffic_states
    
    cleanup_sumo()
    time.sleep(0.5)
    
    # Reset statistics
    traffic_statistics = {
        "total_vehicles_passed": 0,
        "total_simulation_time": 0,
        "congestion_events": [],
        "vehicle_history": [],
        "peak_vehicle_count": 0,
        "average_speed_history": [],
        "start_time": datetime.now().isoformat()
    }
    
    try:
        traci.start(["sumo-gui", "-c", f"sumo_intersection/cfg/{config_file}"])
        sumo_running = True
        
        step_counter = 0
        previous_vehicles = set()
        
        while traci.simulation.getMinExpectedNumber() > 0 and sumo_running:
            traci.simulationStep()
            step_counter += 1
            
            # Apply manual traffic light control if enabled
            if traffic_light_manual_mode:
                apply_manual_traffic_control()
            
            if step_counter % 3 != 0:
                continue
                
            vehicle_ids = traci.vehicle.getIDList()
            current_vehicles = set(vehicle_ids)
            vehicles = []
            
            # Track vehicles that completed their journey
            completed_vehicles = previous_vehicles - current_vehicles
            traffic_statistics["total_vehicles_passed"] += len(completed_vehicles)
            
            # Collect vehicle data and calculate statistics
            total_speed = 0
            slow_vehicles = 0
            
            for veh_id in vehicle_ids:
                try:
                    pos = traci.vehicle.getPosition(veh_id)
                    speed = traci.vehicle.getSpeed(veh_id)
                    
                    vehicles.append({
                        "id": veh_id,
                        "x": round(pos[0], 1),
                        "y": round(pos[1], 1),
                        "speed": round(speed, 1)
                    })
                    
                    total_speed += speed
                    if speed < 2.0:  # Consider vehicles going < 2 m/s as slow
                        slow_vehicles += 1
                        
                except:
                    continue
            
            # Update statistics
            current_time = traci.simulation.getTime()
            traffic_statistics["total_simulation_time"] = current_time
            
            if len(vehicles) > traffic_statistics["peak_vehicle_count"]:
                traffic_statistics["peak_vehicle_count"] = len(vehicles)
            
            # Track average speed
            if len(vehicles) > 0:
                avg_speed = total_speed / len(vehicles)
                traffic_statistics["average_speed_history"].append({
                    "time": current_time,
                    "speed": round(avg_speed, 2),
                    "vehicle_count": len(vehicles)
                })
                
                # Detect congestion events
                if len(vehicles) > 15 or avg_speed < 3.0:
                    traffic_statistics["congestion_events"].append({
                        "time": current_time,
                        "vehicle_count": len(vehicles),
                        "avg_speed": round(avg_speed, 2),
                        "slow_vehicles": slow_vehicles
                    })
            
            # Traffic light data (enhanced for manual mode)
            try:
                tl_ids = traci.trafficlight.getIDList()
                traffic_lights = {}
                
                if tl_ids:
                    main_tl = tl_ids[0]
                    
                    if traffic_light_manual_mode and main_tl in manual_traffic_states:
                        # Use manual state
                        phase = manual_traffic_states[main_tl]
                        # Ensure manual state is applied
                        traci.trafficlight.setRedYellowGreenState(main_tl, phase)
                        traci.trafficlight.setPhaseDuration(main_tl, 999)
                    else:
                        # Use SUMO's automatic state
                        phase = traci.trafficlight.getRedYellowGreenState(main_tl)
                    
                    traffic_lights[main_tl] = {
                        'state': phase,
                        'manual_mode': traffic_light_manual_mode,
                        'program': traci.trafficlight.getProgram(main_tl),
                        'phase_index': traci.trafficlight.getPhase(main_tl)
                    }
                
                simulation_data["traffic_lights"] = traffic_lights
                
            except Exception as e:
                print(f"Traffic light error: {e}")
                simulation_data["traffic_lights"] = {}
            
            simulation_data["vehicles"] = vehicles
            simulation_data["step"] = current_time
            simulation_data["statistics"] = traffic_statistics
            
            previous_vehicles = current_vehicles
            time.sleep(0.05)
            
    except Exception as e:
        print(f"SUMO Error: {e}")
    finally:
        cleanup_sumo()

def apply_manual_traffic_control():
    """Apply manual traffic light control with proper validation"""
    try:
        tl_ids = traci.trafficlight.getIDList()
        if tl_ids and manual_traffic_states:
            main_tl = tl_ids[0]
            if main_tl in manual_traffic_states:
                manual_state = manual_traffic_states[main_tl]
                
                # Validate state before applying (must be valid SUMO format)
                if len(manual_state) >= 4 and all(c in 'rRgGyY' for c in manual_state):
                    # Get current program and phase info
                    current_program = traci.trafficlight.getProgram(main_tl)
                    
                    # Set the state directly
                    traci.trafficlight.setRedYellowGreenState(main_tl, manual_state)
                    
                    # Optional: Keep the simulation running by setting a longer phase duration
                    traci.trafficlight.setPhaseDuration(main_tl, 999)  # Long duration for manual control
                    
    except Exception as e:
        print(f"Traffic light control error: {e}")

@app.get("/")
def dashboard(request: Request):
    """Serve the HTML dashboard"""
    config_files = [f for f in os.listdir(simulation_files_path) if f.endswith(".sumocfg")]

    return templates.TemplateResponse("index.html", {"request": request, "configs": config_files})


    
@app.get("/api/data")
def get_simulation_data():
    """API endpoint to get current simulation data"""
    return simulation_data

@app.get("/api/status")
def get_status():
    """Check if SUMO is running"""
    return {"running": sumo_running}

@app.post("/api/start")
def start_simulation():
    """Start SUMO simulation in background thread"""
    global sumo_running
    if not sumo_running:
        thread = threading.Thread(target=start_sumo, daemon=True)
        thread.start()
        return {"message": "Starting SUMO simulation"}
    return {"message": "SUMO already running"}

@app.post("/api/stop")
def stop_simulation():
    """Stop SUMO simulation"""
    cleanup_sumo()
    return {"message": "SUMO stopped"}

@app.post("/api/select_config")
def select_config(config: ConfigSelect):
    """Select a different SUMO config file"""
    global config_file
    config_file = config.config_name
    return {"message": f"Config set to {config.config_name}"}

# Add this for even better performance:

# Add this optimized endpoint
@app.get("/api/data/fast")
async def get_simulation_data_fast():
    """Ultra-fast API endpoint with minimal processing"""
    return {
        "vehicles": simulation_data.get("vehicles", [])[:50],  # Limit to 50 vehicles
        "step": simulation_data.get("step", 0),
        "traffic_lights": simulation_data.get("traffic_lights", {}),
        "timestamp": time.time()
    }

@app.post("/api/traffic_light/mode")
def set_traffic_light_mode(mode: TrafficLightMode):
    """Enable/disable manual traffic light control with proper connection check"""
    global traffic_light_manual_mode, manual_traffic_states
    
    # Check if SUMO is actually running
    if not sumo_running:
        return {"error": "SUMO simulation is not running. Start simulation first."}
    
    # Test TraCI connection
    try:
        # Try to get traffic light IDs to verify connection
        tl_ids = traci.trafficlight.getIDList()
        if not tl_ids:
            return {"error": "No traffic lights found in simulation"}
        print(f"Found traffic lights: {tl_ids}")
    except Exception as e:
        return {"error": f"TraCI connection error: {e}"}
    
    traffic_light_manual_mode = mode.manual_mode
    
    if mode.manual_mode:
        # When enabling manual mode, initialize all lights to RED
        try:
            main_tl = tl_ids[0]
            print(f"Setting manual control for traffic light: {main_tl}")
            
            # Set all directions to RED initially
            manual_traffic_states[main_tl] = "rrrr"
            
            # Apply the red state immediately
            traci.trafficlight.setRedYellowGreenState(main_tl, "rrrr")
            traci.trafficlight.setPhaseDuration(main_tl, 999)  # Long duration
            
            print(f"Manual mode enabled - All lights set to RED for {main_tl}")
            return {"message": "Manual mode enabled - All lights set to RED"}
            
        except Exception as e:
            traffic_light_manual_mode = False  # Reset on failure
            print(f"Failed to enable manual mode: {e}")
            return {"error": f"Failed to enable manual mode: {e}"}
    else:
        # When disabling manual mode, restore automatic control
        try:
            if tl_ids:
                main_tl = tl_ids[0]
                # Clear manual states
                manual_traffic_states.clear()
                
                # Restore automatic control by setting back to program 0
                traci.trafficlight.setProgram(main_tl, "0")
                
                print("Automatic mode restored")
                return {"message": "Automatic mode restored"}
        except Exception as e:
            print(f"Failed to restore automatic mode: {e}")
            return {"error": f"Failed to restore automatic mode: {e}"}
    
    return {"message": f"Manual mode: {'enabled' if mode.manual_mode else 'disabled'}"}

@app.post("/api/traffic_light/control")
def control_traffic_light(control: TrafficLightControl):
    """Control individual traffic light direction with comprehensive error handling"""
    global manual_traffic_states
    
    # Check if SUMO is running
    if not sumo_running:
        return {"error": "SUMO simulation is not running"}
    
    # Check if manual mode is enabled
    if not traffic_light_manual_mode:
        return {"error": "Manual mode not enabled. Enable manual mode first."}
    
    try:
        # Get traffic light IDs with error handling
        tl_ids = traci.trafficlight.getIDList()
        if not tl_ids:
            return {"error": "No traffic lights found in simulation"}
            
        main_tl = tl_ids[0]
        print(f"Controlling traffic light: {main_tl}")
        
        # Convert direction and state to SUMO format
        direction_map = {"north": 0, "east": 1, "south": 2, "west": 3}
        state_map = {"red": "r", "green": "G", "yellow": "y"}
        
        # Validate inputs
        if control.direction not in direction_map:
            return {"error": f"Invalid direction: {control.direction}. Valid: {list(direction_map.keys())}"}
        if control.state not in state_map:
            return {"error": f"Invalid state: {control.state}. Valid: {list(state_map.keys())}"}
        
        # Initialize manual state if not exists
        if main_tl not in manual_traffic_states:
            manual_traffic_states[main_tl] = "rrrr"  # Default all red
        
        # Update specific direction
        current_state = list(manual_traffic_states[main_tl])
        direction_index = direction_map[control.direction]
        new_state = state_map[control.state]
        
        # Ensure we have enough characters in state
        while len(current_state) <= direction_index:
            current_state.append('r')
        
        current_state[direction_index] = new_state
        new_traffic_state = "".join(current_state)
        manual_traffic_states[main_tl] = new_traffic_state
        
        print(f"Setting {control.direction} to {control.state}")
        print(f"New traffic state: {new_traffic_state}")
        
        # Apply the change immediately with error handling
        traci.trafficlight.setRedYellowGreenState(main_tl, new_traffic_state)
        traci.trafficlight.setPhaseDuration(main_tl, 999)  # Keep long duration
        
        # Verify the change was applied
        current_phase = traci.trafficlight.getRedYellowGreenState(main_tl)
        print(f"Verified traffic light state: {current_phase}")
        
        return {
            "message": f"Set {control.direction} to {control.state}",
            "current_state": new_traffic_state,
            "verified_state": current_phase,
            "success": True
        }
        
    except Exception as e:
        print(f"Traffic light control failed: {e}")
        return {"error": f"Control failed: {str(e)}"}

@app.get("/api/statistics")
def get_traffic_statistics():
    """Get comprehensive traffic statistics"""
    return traffic_statistics

@app.get("/api/traffic_light/status")
def get_traffic_light_status():
    """Get current traffic light mode and states"""
    return {
        "manual_mode": traffic_light_manual_mode,
        "manual_states": manual_traffic_states,
        "current_simulation_data": simulation_data.get("traffic_lights", {})
    }

# Add this to run the server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)