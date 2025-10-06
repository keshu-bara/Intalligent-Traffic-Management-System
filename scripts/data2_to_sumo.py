import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom
import random

def convert_csv_to_sumo_routes(csv_file, output_file):
    """
    Convert CSV traffic data to SUMO route XML file
    """
    
    # Read CSV data
    df = pd.read_csv(csv_file)
    
    # Sort by timestamp for proper departure timing
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%H:%M:%S')
    df = df.sort_values('Timestamp')
    
    # Create root element
    routes = ET.Element('routes')
    
    # Define vehicle type characteristics
    vehicle_types = {
        'Car': {
            'accel': 2.5, 'decel': 4.5, 'sigma': 0.8,
            'length': 4.0, 'colors': ['red', 'blue', 'green', 'yellow', 'white', 'black', 'orange']
        },
        'Motorcycle': {
            'accel': 3.5, 'decel': 5.0, 'sigma': 0.6,
            'length': 2.0, 'colors': ['red', 'blue', 'yellow', 'white', 'black']
        },
        'Bus': {
            'accel': 1.5, 'decel': 3.5, 'sigma': 0.3,
            'length': 12.0, 'colors': ['blue', 'red', 'yellow', 'orange', 'white', 'black']
        },
        'Truck': {
            'accel': 1.2, 'decel': 3.0, 'sigma': 0.2,
            'length': 8.0, 'colors': ['white', 'red', 'blue', 'yellow', 'green', 'black', 'orange']
        },
        'AutoRickshaw': {
            'accel': 2.0, 'decel': 4.0, 'sigma': 0.7,
            'length': 3.0, 'colors': ['yellow', 'green', 'blue', 'white']
        },
        'Bicycle': {
            'accel': 1.0, 'decel': 2.0, 'sigma': 0.5,
            'length': 1.8, 'colors': ['red', 'blue', 'green', 'yellow']
        }
    }
    
    # Color mapping
    color_map = {
        'red': '1,0,0',
        'blue': '0,0,1',
        'green': '0,1,0',
        'yellow': '1,1,0',
        'white': '1,1,1',
        'black': '0,0,0',
        'orange': '1,0.5,0'
    }
    
    # Lane to route mapping
    lane_to_route = {
        1: {'name': 'north_to_south', 'edges': 'A0 C1'},
        2: {'name': 'east_to_west', 'edges': 'D0 B1'},
        3: {'name': 'south_to_north', 'edges': 'C0 A1'},
        4: {'name': 'west_to_east', 'edges': 'B0 D1'}
    }
    
    # Movement adjustments (for turns)
    def get_route_for_movement(lane, movement):
        base_route = lane_to_route[lane]
        
        if movement == 'Straight':
            return base_route
        elif movement == 'Left':
            # Adjust for left turns
            if lane == 1:  # North to East
                return {'name': 'north_to_east', 'edges': 'A0 D1'}
            elif lane == 2:  # East to South
                return {'name': 'east_to_south', 'edges': 'D0 C1'}
            elif lane == 3:  # South to West
                return {'name': 'south_to_west', 'edges': 'C0 B1'}
            elif lane == 4:  # West to North
                return {'name': 'west_to_north', 'edges': 'B0 A1'}
        elif movement == 'Right':
            # Adjust for right turns
            if lane == 1:  # North to West
                return {'name': 'north_to_west', 'edges': 'A0 B1'}
            elif lane == 2:  # East to North
                return {'name': 'east_to_north', 'edges': 'D0 A1'}
            elif lane == 3:  # South to East
                return {'name': 'south_to_east', 'edges': 'C0 D1'}
            elif lane == 4:  # West to South
                return {'name': 'west_to_south', 'edges': 'B0 C1'}
        
        return base_route
    
    # Generate vehicle types and collect unique combinations
    vehicle_type_map = {}
    created_types = set()
    routes_created = set()
    
    # First pass: create all unique vehicle types and routes
    for _, row in df.iterrows():
        vehicle_type = row['Vehicle_Type']
        speed_kmph = row['Speed_kmph']
        max_speed_ms = speed_kmph / 3.6  # Convert km/h to m/s
        
        # Get vehicle characteristics
        if vehicle_type in vehicle_types:
            char = vehicle_types[vehicle_type]
            
            # Assign random color
            color = random.choice(char['colors'])
            color_rgb = color_map[color]
            
            # Create unique type ID
            type_id = f"{vehicle_type.lower()}_{int(max_speed_ms*10):03d}_{color}"
            
            if type_id not in created_types:
                # Create vehicle type element
                vtype = ET.SubElement(routes, 'vType')
                vtype.set('id', type_id)
                vtype.set('accel', str(char['accel']))
                vtype.set('decel', str(char['decel']))
                vtype.set('sigma', str(char['sigma']))
                vtype.set('length', str(char['length']))
                vtype.set('maxSpeed', f"{max_speed_ms:.1f}")
                vtype.set('color', color_rgb)
                
                created_types.add(type_id)
            
            # Store type mapping
            vehicle_type_map[row['Vehicle_ID']] = type_id
        
        # Create route if not exists
        route_info = get_route_for_movement(row['Lane'], row['Movement'])
        route_id = route_info['name']
        
        if route_id not in routes_created:
            route_elem = ET.SubElement(routes, 'route')
            route_elem.set('id', route_id)
            route_elem.set('edges', route_info['edges'])
            routes_created.add(route_id)
    
    # Second pass: create vehicles
    start_time = df['Timestamp'].min()
    
    for _, row in df.iterrows():
        # Calculate departure time in seconds from start
        time_diff = (row['Timestamp'] - start_time).total_seconds()
        depart_time = max(0, int(time_diff))
        
        # Get route for this vehicle
        route_info = get_route_for_movement(row['Lane'], row['Movement'])
        route_id = route_info['name']
        
        # Create vehicle element
        vehicle = ET.SubElement(routes, 'vehicle')
        vehicle.set('id', f"vehicle_{row['Vehicle_ID']:03d}")
        vehicle.set('type', vehicle_type_map[row['Vehicle_ID']])
        vehicle.set('route', route_id)
        vehicle.set('depart', str(depart_time))
        
        # Add optional attributes
        if row['Headway_sec'] > 0:
            vehicle.set('departLane', 'best')
        
        # Add speed if significantly different from type max
        type_max_speed = float([elem.get('maxSpeed') for elem in routes.findall('vType') 
                               if elem.get('id') == vehicle_type_map[row['Vehicle_ID']]][0])
        current_speed = row['Speed_kmph'] / 3.6
        
        if abs(current_speed - type_max_speed) > 2.0:  # If speed differs by more than 2 m/s
            vehicle.set('departSpeed', f"{current_speed:.1f}")
    
    # Create pretty XML
    rough_string = ET.tostring(routes, 'unicode')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="    ")
    
    # Remove empty lines and fix formatting
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"✅ Successfully converted {len(df)} vehicles to {output_file}")
    print(f"📊 Created {len(created_types)} vehicle types")
    print(f"🛣️ Created {len(routes_created)} routes")
    
    # Print statistics
    print("\n📈 Vehicle Distribution:")
    type_counts = df['Vehicle_Type'].value_counts()
    for vtype, count in type_counts.items():
        percentage = (count / len(df)) * 100
        print(f"   {vtype}: {count} vehicles ({percentage:.1f}%)")
    
    print("\n🚦 Lane Distribution:")
    lane_counts = df['Lane'].value_counts()
    for lane, count in lane_counts.items():
        percentage = (count / len(df)) * 100
        direction = ['North', 'East', 'South', 'West'][lane-1]
        print(f"   Lane {lane} ({direction}): {count} vehicles ({percentage:.1f}%)")
    
    print("\n↔️ Movement Distribution:")
    movement_counts = df['Movement'].value_counts()
    for movement, count in movement_counts.items():
        percentage = (count / len(df)) * 100
        print(f"   {movement}: {count} vehicles ({percentage:.1f}%)")

def create_sumo_config(route_file, network_file="network.net.xml", config_file="data2_simulation.sumocfg"):
    """Create SUMO configuration file for the simulation"""
    
    config = ET.Element('configuration')
    
    # Input section
    input_elem = ET.SubElement(config, 'input')
    ET.SubElement(input_elem, 'net-file').set('value', network_file)
    ET.SubElement(input_elem, 'route-files').set('value', route_file)
    
    # Time section
    time_elem = ET.SubElement(config, 'time')
    ET.SubElement(time_elem, 'begin').set('value', '0')
    ET.SubElement(time_elem, 'end').set('value', '3600')
    ET.SubElement(time_elem, 'step-length').set('value', '1')
    
    # Processing section
    processing_elem = ET.SubElement(config, 'processing')
    ET.SubElement(processing_elem, 'time-to-teleport').set('value', '300')
    
    # Output section (optional)
    output_elem = ET.SubElement(config, 'output')
    ET.SubElement(output_elem, 'tripinfo-output').set('value', 'tripinfo.xml')
    ET.SubElement(output_elem, 'summary-output').set('value', 'summary.xml')
    
    # Write config file
    rough_string = ET.tostring(config, 'unicode')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="    ")
    
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"✅ Created SUMO config file: {config_file}")

def validate_conversion(original_csv, generated_routes):
    """Validate the conversion by comparing vehicle counts"""
    
    # Read original data
    df = pd.read_csv(original_csv)
    
    # Parse generated XML
    tree = ET.parse(generated_routes)
    root = tree.getroot()
    
    vehicles = root.findall('vehicle')
    vtypes = root.findall('vType')
    routes_elem = root.findall('route')
    
    print(f"\n🔍 Validation Results:")
    print(f"   Original CSV vehicles: {len(df)}")
    print(f"   Generated XML vehicles: {len(vehicles)}")
    print(f"   Generated vehicle types: {len(vtypes)}")
    print(f"   Generated routes: {len(routes_elem)}")
    
    if len(df) == len(vehicles):
        print("   ✅ Vehicle count matches!")
    else:
        print("   ❌ Vehicle count mismatch!")
    
    # Check time range
    departure_times = [int(v.get('depart', '0')) for v in vehicles]
    if departure_times:
        print(f"   ⏰ Time range: {min(departure_times)}s to {max(departure_times)}s")
        print(f"   📊 Simulation duration: {max(departure_times) - min(departure_times)}s")

# Main execution
if __name__ == "__main__":
    # Configuration
    input_csv = "../data/data2.csv"  # Your CSV file
    output_routes = "../sumo_intersection/routes/data2_vehicles.rou.xml"  # Output route file
    config_file = "../sumo_intersection/cfg/data2_simulation.sumocfg"  # SUMO config file

    try:
        print("🚀 Starting CSV to SUMO conversion...")
        
        # Convert CSV to SUMO routes
        convert_csv_to_sumo_routes(input_csv, output_routes)
        
        # Create SUMO configuration file
        create_sumo_config(output_routes, config_file=config_file)
        
        # Validate conversion
        validate_conversion(input_csv, output_routes)
        
        print(f"\n🎉 Conversion completed successfully!")
        print(f"📁 Generated files:")
        print(f"   - {output_routes} (SUMO route file)")
        print(f"   - {config_file} (SUMO configuration)")
        
        print(f"\n🚦 To run simulation:")
        print(f"   sumo-gui -c {config_file}")
        print(f"   # OR for command line:")
        print(f"   sumo -c {config_file}")
        
    except Exception as e:
        print(f"❌ Error during conversion: {e}")
        import traceback
        traceback.print_exc()