#<!-- filepath: c:\PC\Projects\SIH\scripts\generate_single_vehicle.py -->
import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom

def create_synthetic_data():
    """Create synthetic data for one vehicle"""
    data = {
        'vehicle_id': ['car_001'],
        'vehicle_type': ['car'],
        'route': ['north_to_south'],
        'departure_time': [10],  # seconds
        'max_speed': [15.0],     # m/s
        'color': ['red']
    }
    data = pd.read_csv('../data/vehicles.csv')  # Load data from CSV
    
    df = pd.DataFrame(data)
    print("Synthetic Data Created:")
    print(df)
    return df

def generate_sumo_route_file(df, output_file):
    """Convert dataframe to SUMO route XML file"""
    
    # Create root element
    routes = ET.Element('routes')
    
    # Add vehicle type definition
    vtype = ET.SubElement(routes, 'vType', 
                         id='car',
                         accel='2.5',
                         decel='4.5', 
                         sigma='0.8',
                         length='4.0',
                         maxSpeed=str(df.iloc[0]['max_speed']),
                         color='1,0,0')
    
    # Add route definition
    route = ET.SubElement(routes, 'route',
                         id='north_to_south',
                         edges='A0 C1')
    
    # Add single vehicle from data
    for index, row in df.iterrows():
        vehicle = ET.SubElement(routes, 'vehicle',
                               id=row['vehicle_id'],
                               type=row['vehicle_type'],
                               route=row['route'],
                               depart=str(row['departure_time']))
    
    # Write to XML file
    rough_string = ET.tostring(routes, 'unicode')
    reparsed = minidom.parseString(rough_string)
    
    with open(output_file, 'w') as f:
        f.write(reparsed.toprettyxml(indent="    "))
    
    print(f"SUMO route file created: {output_file}")

if __name__ == "__main__":
    # Step 1: Create synthetic data
    synthetic_df = create_synthetic_data()
    
    # Step 2: Generate SUMO route file
    output_path = '../sumo_intersection/routes/single_vehicle_routes.rou.xml'
    generate_sumo_route_file(synthetic_df, output_path)
    
    print("✅ Single vehicle route file generated successfully!")