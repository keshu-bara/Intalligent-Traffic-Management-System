import traci
import time

sumo_cmd = ["sumo-gui", "-c", "C:\\PC\\Projects\\SIH2\\sumo_intersection\\cfg\\csv_vehicles.sumocfg"]
traci.start(sumo_cmd)




try:
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        time.sleep(0.1)


finally:
    traci.close()



