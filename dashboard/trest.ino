#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <WiFiUdp.h>

// WiFi credentials
const char* ssid = "Galaxy";
const char* password = "keshubara";

// Server setup
WebServer server(80);
WiFiUDP udp;
const int udpPort = 8888;

// Define the LED pins - YOUR CONFIGURATION
//direction A0 (North)
const int A0_GREEN = 23;   // ledPin1
const int A0_YELLOW = 22;  // ledPin2  
const int A0_RED = 21;     // ledPin3

//direction B0 (South) 
const int B0_GREEN = 19;   // ledPin4
const int B0_YELLOW = 18;  // ledPin5
const int B0_RED = 5;      // ledPin6

//direction C0 (East)
const int C0_GREEN = 25;   // ledPin7
const int C0_YELLOW = 26;  // ledPin8
const int C0_RED = 27;     // ledPin9

//direction D0 (West)
const int D0_GREEN = 12;   // ledPin10
const int D0_YELLOW = 13;  // ledPin11
const int D0_RED = 14;     // ledPin12

// Buzzer pin
const int BUZZER_PIN = 2;

// Current traffic light state
struct TrafficState {
  String phaseState;
  int duration;
  bool emergency;
  bool northLights[3];   // A0: [G, Y, R]
  bool southLights[3];   // B0: [G, Y, R]  
  bool eastLights[3];    // C0: [G, Y, R]
  bool westLights[3];    // D0: [G, Y, R]
} currentState;

void setup() {
  Serial.begin(115200);
  
  // Initialize all LED pins as OUTPUT
  pinMode(A0_GREEN, OUTPUT);
  pinMode(A0_YELLOW, OUTPUT);
  pinMode(A0_RED, OUTPUT);
  
  pinMode(B0_GREEN, OUTPUT);
  pinMode(B0_YELLOW, OUTPUT);
  pinMode(B0_RED, OUTPUT);
  
  pinMode(C0_GREEN, OUTPUT);
  pinMode(C0_YELLOW, OUTPUT);
  pinMode(C0_RED, OUTPUT);
  
  pinMode(D0_GREEN, OUTPUT);
  pinMode(D0_YELLOW, OUTPUT);
  pinMode(D0_RED, OUTPUT);
  
  pinMode(BUZZER_PIN, OUTPUT);
  
  Serial.println("🚦 ESP32 Traffic Light Controller Starting...");
  Serial.println("📍 Pin Configuration:");
  Serial.println("A0(North): G=23, Y=22, R=21");
  Serial.println("B0(South): G=19, Y=18, R=5");
  Serial.println("C0(East):  G=25, Y=26, R=27");
  Serial.println("D0(West):  G=12, Y=13, R=14");
  
  // Connect to WiFi
  Serial.println("\n🔄 Connecting to WiFi...");
  Serial.print("Network: ");
  Serial.println(ssid);
  
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(1000);
    Serial.print(".");
    attempts++;
    
    if (attempts % 10 == 0) {
      Serial.println("\n⏳ Still connecting... (" + String(attempts) + "/30)");
    }
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi Connected Successfully!");
    Serial.println("📶 Network: " + WiFi.SSID());
    Serial.print("🌐 ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("📡 Signal Strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    Serial.println("\n🔗 COPY THIS IP TO YOUR PYTHON CODE:");
    Serial.println("esp32_ip = \"" + WiFi.localIP().toString() + "\"");
  } else {
    Serial.println("\n❌ WiFi Connection Failed!");
    Serial.println("🔍 Check these:");
    Serial.println("  - Galaxy hotspot is ON");
    Serial.println("  - Password 'keshubara' is correct");
    Serial.println("  - ESP32 is near your phone");
    return;
  }
  
  // Setup HTTP endpoints for SUMO communication
  server.on("/update", HTTP_POST, handleTrafficUpdate);
  server.on("/metrics", HTTP_POST, handleMetrics);
  server.on("/emergency", HTTP_POST, handleEmergency);
  server.on("/test", HTTP_POST, handleConnectionTest);
  server.on("/status", HTTP_GET, handleStatus);
  
  server.begin();
  udp.begin(udpPort);
  
  Serial.println("🚀 Web Server Started on Port 80");
  Serial.println("📡 UDP Server Started on Port 8888");
  Serial.println("🎯 Ready to receive SUMO simulation data!");
  
  // Initial state - all red
  setAllRed();
  
  // Test LEDs to verify wiring
  testAllLEDs();
}

void loop() {
  server.handleClient();
  handleUDPMessages();
  
  if (currentState.emergency) {
    blinkEmergencyPattern();
  }
  
  delay(10);
}

void handleTrafficUpdate() {
  if (server.hasArg("plain")) {
    String body = server.arg("plain");
    DynamicJsonDocument doc(1024);
    
    Serial.println("\n📨 Received SUMO Data:");
    Serial.println(body);
    
    if (deserializeJson(doc, body) == DeserializationError::Ok) {
      String phase_state = doc["phase_state"].as<String>();
      int duration = doc["duration_seconds"];
      
      currentState.phaseState = phase_state;
      currentState.duration = duration;
      
      // Check for emergency
      JsonObject commands = doc["commands"];
      if (commands["buzzer_alert"]) {
        currentState.emergency = true;
        soundBuzzer(2, 200);
      } else {
        currentState.emergency = false;
      }
      
      // Apply phase to LEDs
      parseAndApplyPhaseState(phase_state);
      
      Serial.println("✅ Phase Applied: " + phase_state);
      Serial.println("⏱️  Duration: " + String(duration) + "s");
      
      server.send(200, "application/json", "{\"status\":\"success\"}");
    } else {
      Serial.println("❌ Invalid JSON received");
      server.send(400, "application/json", "{\"status\":\"error\"}");
    }
  }
}

void handleConnectionTest() {
  Serial.println("🔗 Connection test from SUMO");
  testAllLEDs();
  
  DynamicJsonDocument response(256);
  response["status"] = "connected";
  response["device"] = "ESP32 Traffic Controller";
  response["ip"] = WiFi.localIP().toString();
  
  String jsonString;
  serializeJson(response, jsonString);
  server.send(200, "application/json", jsonString);
}

void handleStatus() {
  DynamicJsonDocument status(512);
  status["current_phase"] = currentState.phaseState;
  status["duration"] = currentState.duration;
  status["uptime"] = millis();
  
  String jsonString;
  serializeJson(status, jsonString);
  server.send(200, "application/json", jsonString);
}

void handleMetrics() {
  // Handle traffic metrics from SUMO
  server.send(200, "application/json", "{\"status\":\"success\"}");
}

void handleEmergency() {
  // Handle emergency signals
  currentState.emergency = true;
  flashAllYellow(3, 200);
  soundBuzzer(3, 300);
  server.send(200, "application/json", "{\"status\":\"handled\"}");
}

void handleUDPMessages() {
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char buffer[256];
    int len = udp.read(buffer, sizeof(buffer) - 1);
    buffer[len] = '\0';
    Serial.println("📡 UDP: " + String(buffer));
  }
}

void parseAndApplyPhaseState(String phaseState) {
  if (phaseState.length() != 12) {
    Serial.println("❌ Invalid phase length");
    setAllRed();
    return;
  }
  
  // Phase format: NNNEEEWWWSSS (North, East, West, South)
  // Characters 0-2: North (A0)
  currentState.northLights[0] = (phaseState.charAt(0) == 'G');
  currentState.northLights[1] = (phaseState.charAt(1) == 'Y');
  currentState.northLights[2] = (phaseState.charAt(2) == 'r');
  
  // Characters 3-5: East (C0)
  currentState.eastLights[0] = (phaseState.charAt(3) == 'G');
  currentState.eastLights[1] = (phaseState.charAt(4) == 'Y');
  currentState.eastLights[2] = (phaseState.charAt(5) == 'r');
  
  // Characters 6-8: West (D0)
  currentState.westLights[0] = (phaseState.charAt(6) == 'G');
  currentState.westLights[1] = (phaseState.charAt(7) == 'Y');
  currentState.westLights[2] = (phaseState.charAt(8) == 'r');
  
  // Characters 9-11: South (B0)
  currentState.southLights[0] = (phaseState.charAt(9) == 'G');
  currentState.southLights[1] = (phaseState.charAt(10) == 'Y');
  currentState.southLights[2] = (phaseState.charAt(11) == 'r');
  
  applyToLEDs();
  printLEDStatus();
}

void applyToLEDs() {
  // North (A0)
  digitalWrite(A0_GREEN, currentState.northLights[0] ? HIGH : LOW);
  digitalWrite(A0_YELLOW, currentState.northLights[1] ? HIGH : LOW);
  digitalWrite(A0_RED, currentState.northLights[2] ? HIGH : LOW);
  
  // South (B0)
  digitalWrite(B0_GREEN, currentState.southLights[0] ? HIGH : LOW);
  digitalWrite(B0_YELLOW, currentState.southLights[1] ? HIGH : LOW);
  digitalWrite(B0_RED, currentState.southLights[2] ? HIGH : LOW);
  
  // East (C0)
  digitalWrite(C0_GREEN, currentState.eastLights[0] ? HIGH : LOW);
  digitalWrite(C0_YELLOW, currentState.eastLights[1] ? HIGH : LOW);
  digitalWrite(C0_RED, currentState.eastLights[2] ? HIGH : LOW);
  
  // West (D0)
  digitalWrite(D0_GREEN, currentState.westLights[0] ? HIGH : LOW);
  digitalWrite(D0_YELLOW, currentState.westLights[1] ? HIGH : LOW);
  digitalWrite(D0_RED, currentState.westLights[2] ? HIGH : LOW);
}

void printLEDStatus() {
  Serial.println("🚦 LED Status:");
  Serial.print("A0(North): ");
  if (currentState.northLights[0]) Serial.print("G(23) ");
  if (currentState.northLights[1]) Serial.print("Y(22) ");
  if (currentState.northLights[2]) Serial.print("R(21) ");
  Serial.println();
  
  Serial.print("B0(South): ");
  if (currentState.southLights[0]) Serial.print("G(19) ");
  if (currentState.southLights[1]) Serial.print("Y(18) ");
  if (currentState.southLights[2]) Serial.print("R(5) ");
  Serial.println();
  
  Serial.print("C0(East):  ");
  if (currentState.eastLights[0]) Serial.print("G(25) ");
  if (currentState.eastLights[1]) Serial.print("Y(26) ");
  if (currentState.eastLights[2]) Serial.print("R(27) ");
  Serial.println();
  
  Serial.print("D0(West):  ");
  if (currentState.westLights[0]) Serial.print("G(12) ");
  if (currentState.westLights[1]) Serial.print("Y(13) ");
  if (currentState.westLights[2]) Serial.print("R(14) ");
  Serial.println();
}

void setAllRed() {
  digitalWrite(A0_GREEN, LOW); digitalWrite(A0_YELLOW, LOW); digitalWrite(A0_RED, HIGH);
  digitalWrite(B0_GREEN, LOW); digitalWrite(B0_YELLOW, LOW); digitalWrite(B0_RED, HIGH);
  digitalWrite(C0_GREEN, LOW); digitalWrite(C0_YELLOW, LOW); digitalWrite(C0_RED, HIGH);
  digitalWrite(D0_GREEN, LOW); digitalWrite(D0_YELLOW, LOW); digitalWrite(D0_RED, HIGH);
  
  Serial.println("🔴 All RED");
}

void testAllLEDs() {
  Serial.println("🧪 Testing LEDs...");
  
  // Test each LED briefly
  int pins[] = {23,22,21, 19,18,5, 25,26,27, 12,13,14};
  String names[] = {"A0-G","A0-Y","A0-R", "B0-G","B0-Y","B0-R", 
                   "C0-G","C0-Y","C0-R", "D0-G","D0-Y","D0-R"};
  
  for (int i = 0; i < 12; i++) {
    Serial.print("Testing " + names[i] + " (Pin " + String(pins[i]) + ")... ");
    digitalWrite(pins[i], HIGH);
    delay(200);
    digitalWrite(pins[i], LOW);
    Serial.println("✓");
  }
  
  Serial.println("✅ LED test complete");
}

void flashAllYellow(int count, int delayMs) {
  for (int i = 0; i < count; i++) {
    digitalWrite(A0_YELLOW, HIGH);
    digitalWrite(B0_YELLOW, HIGH);
    digitalWrite(C0_YELLOW, HIGH);
    digitalWrite(D0_YELLOW, HIGH);
    delay(delayMs);
    
    digitalWrite(A0_YELLOW, LOW);
    digitalWrite(B0_YELLOW, LOW);
    digitalWrite(C0_YELLOW, LOW);
    digitalWrite(D0_YELLOW, LOW);
    delay(delayMs);
  }
  applyToLEDs();
}

void blinkEmergencyPattern() {
  static unsigned long lastBlink = 0;
  static bool blinkState = false;
  
  if (millis() - lastBlink > 500) {
    blinkState = !blinkState;
    digitalWrite(A0_YELLOW, blinkState ? HIGH : LOW);
    digitalWrite(B0_YELLOW, blinkState ? HIGH : LOW);
    digitalWrite(C0_YELLOW, blinkState ? HIGH : LOW);
    digitalWrite(D0_YELLOW, blinkState ? HIGH : LOW);
    lastBlink = millis();
  }
}

void soundBuzzer(int count, int duration) {
  for (int i = 0; i < count; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(duration);
    digitalWrite(BUZZER_PIN, LOW);
    delay(100);
  }
}