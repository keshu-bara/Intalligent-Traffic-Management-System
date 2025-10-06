# # Simple test to verify SUMO config and TraCI connection
# import traci
# import time

# def test_sumo_connection():
#     """Test basic SUMO connection with your existing config"""
#     try:
#         print("Starting SUMO with csv_vehicles.sumocfg...")
        
#         # Start SUMO with your config file
#         traci.start(["sumo-gui", "-c", "sumo_intersection/cfg/csv_vehicles.sumocfg"])
        
#         print("✓ SUMO connected successfully!")
#         print("✓ Config file loaded:", "csv_vehicles.sumocfg")
        
#         # Run a few simulation steps
#         for step in range(10):
#             traci.simulationStep()
#             vehicles = traci.vehicle.getIDList()
#             print(f"Step {step}: {len(vehicles)} vehicles in simulation")
            
#             if vehicles:
#                 # Show data for first vehicle
#                 veh = vehicles[0]
#                 pos = traci.vehicle.getPosition(veh)
#                 speed = traci.vehicle.getSpeed(veh)
#                 print(f"  Vehicle {veh}: Position({pos[0]:.1f}, {pos[1]:.1f}), Speed: {speed:.2f} m/s")
            
#             time.sleep(0.5)
        
#         print("\n✓ TraCI communication working!")
        
#     except Exception as e:
#         print(f"❌ Error: {e}")
#     finally:
#         try:
#             traci.close()
#             print("✓ SUMO connection closed")
#         except:
#             pass

# if __name__ == "__main__":
#     test_sumo_connection()

import os

print(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))