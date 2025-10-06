import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom

def load_csv_data():
    """Load vehicle data from CSV file and sort by departure time"""
    try:
        df = pd.read_csv('../data/data2.csv')
        
        # Sort by departure_time - THIS IS CRITICAL for SUMO
        df = df.sort_values('departure_time').reset_index(drop=True)
        
        print("CSV Data Loaded and Sorted:")
        print(f"Total vehicles: {len(df)}")
        print(f"Vehicle types: {df['vehicle_type'].unique()}")
        print(f"Routes: {df['route'].unique()}")
        print(f"Departure time range: {df['departure_time'].min()} - {df['departure_time'].max()}")
        print("\nFirst 5 vehicles (sorted by departure time):")
        print(df[['vehicle_id', 'departure_time', 'vehicle_type', 'route']].head())
        return df
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return pd.DataFrame()

def generate_sumo_route_file(df, output_file):
    """Convert sorted CSV dataframe to SUMO route XML file"""
    
    # Create root element
    routes = ET.Element('routes')
    
    # Define vehicle type characteristics for all types in CSV
    vehicle_characteristics = {
        'car': {
            'accel': '2.5', 'decel': '4.5', 'sigma': '0.8', 
            'length': '4.0', 'maxSpeed': '15.0', 'color': '1,0,0'
        },
        'truck': {
            'accel': '1.2', 'decel': '3.0', 'sigma': '0.2', 
            'length': '8.0', 'maxSpeed': '12.0', 'color': '0.5,0.5,0.5'
        },
        'bus': {
            'accel': '1.5', 'decel': '3.5', 'sigma': '0.3', 
            'length': '12.0', 'maxSpeed': '13.0', 'color': '0,1,0'
        },
        'motorcycle': {
            'accel': '3.5', 'decel': '6.0', 'sigma': '0.9', 
            'length': '2.0', 'maxSpeed': '18.0', 'color': '0,0,1', 'width': '0.8'
        },
        'autorickshaw': {
            'accel': '2.0', 'decel': '4.0', 'sigma': '0.7', 
            'length': '3.2', 'maxSpeed': '12.0', 'color': '1,1,0', 'width': '1.4'
        }
    }
    
    # Color mapping from CSV colors to RGB
    color_map = {
        'red': '1,0,0', 'green': '0,1,0', 'blue': '0,0,1',
        'yellow': '1,1,0', 'orange': '1,0.5,0', 'white': '1,1,1', 
        'black': '0,0,0', 'purple': '0.5,0,0.5', 'cyan': '0,1,1'
    }
    
    # Create vehicle types for each unique combination
    unique_combinations = df[['vehicle_type', 'max_speed', 'color']].drop_duplicates()
    
    for _, row in unique_combinations.iterrows():
        vtype_id = f"{row['vehicle_type']}_{int(row['max_speed']*10)}_{row['color']}"
        
        # Get base characteristics
        if row['vehicle_type'] in vehicle_characteristics:
            attrs = vehicle_characteristics[row['vehicle_type']].copy()
        else:
            # Default characteristics if type not found
            attrs = vehicle_characteristics['car'].copy()
        
        # Override with CSV data
        attrs['id'] = vtype_id
        attrs['maxSpeed'] = str(row['max_speed'])
        attrs['color'] = color_map.get(row['color'], '0.5,0.5,0.5')
        
        # Create vType element
        vtype = ET.SubElement(routes, 'vType', **attrs)
    
    # Define all possible routes
    route_definitions = {
        'north_to_south': 'A0 C1',
        'north_to_east': 'A0 D1', 
        'north_to_west': 'A0 B1',
        'south_to_north': 'C0 A1',
        'south_to_east': 'C0 D1',
        'south_to_west': 'C0 B1', 
        'east_to_west': 'D0 B1',
        'east_to_north': 'D0 A1',
        'east_to_south': 'D0 C1',
        'west_to_east': 'B0 D1',
        'west_to_north': 'B0 A1',
        'west_to_south': 'B0 C1'
    }
    
    # Add route definitions
    unique_routes = df['route'].unique()
    for route_id in unique_routes:
        if route_id in route_definitions:
            route = ET.SubElement(routes, 'route',
                                 id=route_id,
                                 edges=route_definitions[route_id])
        else:
            print(f"Warning: Route '{route_id}' not defined in route_definitions")
    
    # Add individual vehicles from CSV data (already sorted by departure time)
    print(f"\nAdding {len(df)} vehicles in departure time order...")
    
    for i, row in df.iterrows():
        # Create custom vehicle type ID
        vtype_id = f"{row['vehicle_type']}_{int(row['max_speed']*10)}_{row['color']}"
        
        vehicle_attrs = {
            'id': row['vehicle_id'],
            'type': vtype_id,
            'route': row['route'],
            'depart': str(int(row['departure_time']))  # Ensure integer departure time
        }
        
        vehicle = ET.SubElement(routes, 'vehicle', **vehicle_attrs)
        
        # Print progress for first few and last few vehicles
        if i < 5 or i >= len(df) - 5:
            print(f"  Vehicle {i+1}: {row['vehicle_id']} departs at {row['departure_time']}s")
    
    # Write to XML file
    rough_string = ET.tostring(routes, 'unicode')
    reparsed = minidom.parseString(rough_string)
    
    with open(output_file, 'w') as f:
        f.write(reparsed.toprettyxml(indent="    "))
    
    print(f"\nSUMO route file created: {output_file}")
    print(f"Created {len(unique_combinations)} vehicle types")
    print(f"Created {len(df)} vehicles (sorted by departure time)")

def validate_sorting(df):
    """Validate that vehicles are properly sorted"""
    is_sorted = df['departure_time'].is_monotonic_increasing
    print(f"\n✅ Departure times properly sorted: {is_sorted}")
    
    if not is_sorted:
        print("❌ ERROR: Vehicles are not sorted by departure time!")
        print("This will cause SUMO to ignore vehicles.")
        return False
    
    return True

if __name__ == "__main__":
    # Step 1: Load and sort CSV data
    csv_df = load_csv_data()
    
    if not csv_df.empty:
        # Step 2: Validate sorting
        if validate_sorting(csv_df):
            # Step 3: Generate SUMO route file
            output_path = '../sumo_intersection/routes/csv_vehicles_sorted.rou.xml'
            generate_sumo_route_file(csv_df, output_path)
            
            print("\n✅ CSV to SUMO conversion completed successfully!")
            print(f"📊 Processed {len(csv_df)} vehicles from CSV")
            print("🔧 All vehicles are now sorted by departure time")
        else:
            print("❌ Fix sorting issues before generating SUMO file")
    else:
        print("❌ No data loaded from CSV file")