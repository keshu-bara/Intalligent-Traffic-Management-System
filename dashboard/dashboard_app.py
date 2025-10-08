import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import time
import os
import numpy as np

# Configure Streamlit page
st.set_page_config(
    page_title="Smart Traffic Light Dashboard",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dashboard configuration
DASHBOARD_DATA_DIR = "dashboard_data"
REFRESH_INTERVAL = 2  # seconds

class DashboardDataReader:
    def __init__(self, data_dir=DASHBOARD_DATA_DIR):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
    
    def read_json_file(self, filename):
        """Read JSON file safely"""
        filepath = os.path.join(self.data_dir, filename)
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    return json.load(f)
            return []
        except:
            return []
    
    def get_current_state(self):
        """Get current traffic state"""
        states = self.read_json_file("traffic_states.json")
        return states[-1] if states else None
    
    def get_performance_data(self, limit=50):
        """Get performance metrics"""
        return self.read_json_file("performance.json")[-limit:]
    
    def get_phase_history(self, limit=20):
        """Get phase change history"""
        return self.read_json_file("phase_changes.json")[-limit:]
    
    def get_reward_data(self, limit=30):
        """Get reward breakdown data"""
        return self.read_json_file("rewards.json")[-limit:]

def main():
    st.title("🚦 Smart Traffic Light Control Dashboard")
    st.sidebar.title("Dashboard Controls")
    
    # Initialize data reader
    reader = DashboardDataReader()
    
    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto Refresh", value=True)
    refresh_interval = st.sidebar.slider("Refresh Interval (s)", 1, 10, REFRESH_INTERVAL)
    
    # Manual refresh button
    if st.sidebar.button("🔄 Refresh Now"):
        st.experimental_rerun()
    
    # Create main layout
    col1, col2 = st.columns([2, 1])
    
    with col1:
        display_traffic_state(reader)
        display_performance_metrics(reader)
    
    with col2:
        display_phase_history(reader)
        display_reward_analysis(reader)
    
    # Bottom section - full width
    display_traffic_trends(reader)
    
    # Auto-refresh mechanism
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()

def display_traffic_state(reader):
    """Display current traffic state"""
    st.subheader("🚗 Current Traffic State")
    
    current_state = reader.get_current_state()
    
    if current_state:
        # Traffic metrics
        traffic_data = current_state.get('traffic_data', {})
        
        # Create 4 columns for directions
        col1, col2, col3, col4 = st.columns(4)
        
        directions = ['north', 'south', 'east', 'west']
        direction_icons = ['⬆️', '⬇️', '➡️', '⬅️']
        cols = [col1, col2, col3, col4]
        
        for i, (direction, icon, col) in enumerate(zip(directions, direction_icons, cols)):
            data = traffic_data.get(direction, {})
            
            with col:
                st.metric(
                    label=f"{icon} {direction.title()}",
                    value=f"{data.get('vehicle_count', 0):.1f}",
                    delta=f"{data.get('congestion_ratio', 0)*100:.0f}% congested"
                )
                
                # Speed indicator
                speed = data.get('avg_speed_kmh', 0)
                if speed > 30:
                    speed_status = "🟢 Good"
                elif speed > 15:
                    speed_status = "🟡 Slow"
                else:
                    speed_status = "🔴 Congested"
                
                st.write(f"Speed: {speed:.1f} km/h {speed_status}")
        
        # Summary metrics
        summary = current_state.get('summary', {})
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Vehicles", summary.get('total_vehicles', 0))
        with col2:
            st.metric("Total Congestion", f"{summary.get('total_congestion', 0):.2f}")
        with col3:
            st.metric("Avg Speed", f"{summary.get('avg_speed', 0)*54:.1f} km/h")
        with col4:
            st.metric("Busiest Direction", summary.get('busiest_direction', 'N/A'))
        
        # Last updated
        timestamp = current_state.get('timestamp', '')
        if timestamp:
            st.caption(f"Last updated: {timestamp}")
    
    else:
        st.warning("No traffic data available. Make sure the simulation is running.")

def display_performance_metrics(reader):
    """Display performance metrics and trends"""
    st.subheader("📈 Performance Metrics")
    
    performance_data = reader.get_performance_data(30)
    
    if performance_data:
        # Create DataFrame
        df = pd.DataFrame(performance_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Extract metrics
        metrics = pd.json_normalize(df['metrics'])
        df = pd.concat([df[['timestamp', 'step']], metrics], axis=1)
        
        # Performance charts
        col1, col2 = st.columns(2)
        
        with col1:
            # Reward trend
            fig_reward = go.Figure()
            fig_reward.add_trace(go.Scatter(
                x=df['step'],
                y=df['average_reward_last_50'],
                mode='lines+markers',
                name='Avg Reward (Last 50)',
                line=dict(color='#2E8B57', width=3)
            ))
            fig_reward.update_layout(
                title="Reward Trend",
                xaxis_title="Simulation Step",
                yaxis_title="Average Reward",
                height=300
            )
            st.plotly_chart(fig_reward, use_container_width=True)
        
        with col2:
            # Congestion trend
            fig_congestion = go.Figure()
            fig_congestion.add_trace(go.Scatter(
                x=df['step'],
                y=df['current_congestion_level'],
                mode='lines+markers',
                name='Congestion Level',
                line=dict(color='#DC143C', width=3)
            ))
            fig_congestion.update_layout(
                title="Congestion Level",
                xaxis_title="Simulation Step",
                yaxis_title="Congestion Level",
                height=300
            )
            st.plotly_chart(fig_congestion, use_container_width=True)
        
        # Latest metrics
        latest = performance_data[-1]['metrics']
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Memory Size", latest.get('dqn_memory_size', 0))
        with col2:
            epsilon = latest.get('exploration_rate', 0)
            st.metric("Exploration Rate", f"{epsilon:.3f}" if epsilon else "N/A")
        with col3:
            learning_status = "🔍 Exploring" if epsilon and epsilon > 0.3 else "🎯 Exploiting"
            st.metric("Learning Status", learning_status)
    
    else:
        st.info("No performance data available yet.")

def display_phase_history(reader):
    """Display recent phase changes"""
    st.subheader("🔄 Recent Phase Changes")
    
    phase_data = reader.get_phase_history(10)
    
    if phase_data:
        for phase in reversed(phase_data[-5:]):  # Show last 5 phases
            timestamp = datetime.fromisoformat(phase['timestamp']).strftime("%H:%M:%S")
            direction = phase.get('direction', 'Unknown')
            duration = phase.get('duration_seconds', 0)
            step = phase.get('step', 0)
            
            # Direction icon
            icons = {'North': '⬆️', 'South': '⬇️', 'East': '➡️', 'West': '⬅️'}
            icon = icons.get(direction, '🚦')
            
            # Validation info
            validation = phase.get('validation_info', {})
            reason = validation.get('decision_reason', 'DQN decision')
            
            with st.container():
                st.write(f"**{timestamp}** - Step {step}")
                st.write(f"{icon} {direction} Green for {duration}s")
                st.write(f"📊 {reason}")
                if validation.get('chosen_direction_traffic', 0) > 0:
                    traffic = validation['chosen_direction_traffic']
                    congestion = validation.get('chosen_direction_congestion', 0)
                    st.write(f"🚗 Traffic: {traffic:.2f}, Congestion: {congestion:.2f}")
                st.divider()
    
    else:
        st.info("No phase change data available.")

def display_reward_analysis(reader):
    """Display reward breakdown analysis"""
    st.subheader("💰 Reward Analysis")
    
    reward_data = reader.get_reward_data(10)
    
    if reward_data:
        latest_reward = reward_data[-1]
        
        # Total reward
        total_reward = latest_reward.get('total_reward', 0)
        st.metric("Latest Total Reward", f"{total_reward:.2f}")
        
        # Reward breakdown
        breakdown = latest_reward.get('reward_breakdown', {})
        
        if breakdown:
            # Create bar chart
            components = list(breakdown.keys())
            values = list(breakdown.values())
            
            colors = ['green' if v > 0 else 'red' for v in values]
            
            fig_rewards = go.Figure(data=[
                go.Bar(x=components, y=values, marker_color=colors)
            ])
            
            fig_rewards.update_layout(
                title="Reward Components",
                xaxis_title="Component",
                yaxis_title="Reward Value",
                height=300,
                xaxis_tickangle=-45
            )
            
            st.plotly_chart(fig_rewards, use_container_width=True)
        
        # Analysis
        analysis = latest_reward.get('reward_analysis', {})
        if analysis:
            st.write("**Analysis:**")
            dominant = analysis.get('dominant_factor', 'None')
            st.write(f"🎯 Dominant factor: {dominant}")
            
            positive = analysis.get('positive_factors', [])
            if positive:
                st.write(f"✅ Positive: {', '.join(positive)}")
            
            negative = analysis.get('negative_factors', [])
            if negative:
                st.write(f"❌ Negative: {', '.join(negative)}")
    
    else:
        st.info("No reward data available.")

def display_traffic_trends(reader):
    """Display traffic trends over time"""
    st.subheader("📊 Traffic Trends")
    
    states = reader.read_json_file("traffic_states.json")
    
    if len(states) > 5:
        # Process data
        timestamps = []
        north_traffic = []
        south_traffic = []
        east_traffic = []
        west_traffic = []
        
        for state in states[-50:]:  # Last 50 data points
            timestamps.append(datetime.fromisoformat(state['timestamp']))
            traffic_data = state.get('traffic_data', {})
            
            north_traffic.append(traffic_data.get('north', {}).get('vehicle_count', 0))
            south_traffic.append(traffic_data.get('south', {}).get('vehicle_count', 0))
            east_traffic.append(traffic_data.get('east', {}).get('vehicle_count', 0))
            west_traffic.append(traffic_data.get('west', {}).get('vehicle_count', 0))
        
        # Create multi-line chart
        fig_trends = go.Figure()
        
        fig_trends.add_trace(go.Scatter(x=timestamps, y=north_traffic, name='⬆️ North', line=dict(color='blue')))
        fig_trends.add_trace(go.Scatter(x=timestamps, y=south_traffic, name='⬇️ South', line=dict(color='red')))
        fig_trends.add_trace(go.Scatter(x=timestamps, y=east_traffic, name='➡️ East', line=dict(color='green')))
        fig_trends.add_trace(go.Scatter(x=timestamps, y=west_traffic, name='⬅️ West', line=dict(color='orange')))
        
        fig_trends.update_layout(
            title="Traffic Volume Trends by Direction",
            xaxis_title="Time",
            yaxis_title="Vehicle Count",
            height=400,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig_trends, use_container_width=True)
    
    else:
        st.info("Collecting traffic trend data...")

if __name__ == "__main__":
    main()