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

// Traffic Light GPIO Pins for A0, B0, C0, D0
// A0 (North) - Pins
const int A0_GREEN = 23;
const int A0_YELLOW = 22;
const int A0_RED = 21;

// B0 (South) - Pins  
const int B0_GREEN = 19;
const int B0_YELLOW = 18;
const int B0_RED = 5;

// C0 (East) - Pins
const int C0_GREEN = 25;
const int C0_YELLOW = 28;
const int C0_RED = 27;

// D0 (West) - Pins
const int D0_GREEN = 12;
const int D0_YELLOW = 13;
const int D0_RED = 14;

// Buzzer pin
const int BUZZER_PIN = 2;

/* PHASE STATE FORMAT FROM SIMULATION:
 * Phase state is 12 characters representing 4 directions × 3 lights each:
 * 
 * Characters 0-2:  North (A0) - [Green, Yellow, Red]
 * Characters 3-5:  East  (C0) - [Green, Yellow, Red]  
 * Characters 6-8:  West  (D0) - [Green, Yellow, Red]
 * Characters 9-11: South (B0) - [Green, Yellow, Red]
 * 
 * Examples:
 * "GGGrrrrrrrrr" = North Green (G at pos 0), others Red (r)
 * "rrrGGGrrrrrr" = East Green (G at pos 3-5), others Red
 * "rrrrrrrrrGGG" = South Green (G at pos 9-11), others Red
 * "rrrrrGGGrrrr" = West Green (G at pos 6-8), others Red
 * 
 * 'G' = Green light ON
 * 'Y' = Yellow light ON  
 * 'r' = Red light ON (or light OFF)
 */

// Current traffic light state
struct TrafficState {
  String phaseState;     // 12-character phase state
  int duration;
  bool emergency;
  
  // Parsed state for each direction [Green, Yellow, Red]
  bool northLights[3];   // A0: [G, Y, R]
  bool eastLights[3];    // C0: [G, Y, R]
  bool westLights[3];    // D0: [G, Y, R]
  bool southLights[3];   // B0: [G, Y, R]
} currentState;

void setup() {
  Serial.begin(115200);
  
  // Initialize all GPIO pins as OUTPUT
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
  
  // Connect to WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  
  Serial.println("WiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
  
  // Setup HTTP endpoints
  server.on("/update", HTTP_POST, handleTrafficUpdate);
  server.on("/metrics", HTTP_POST, handleMetrics);
  server.on("/emergency", HTTP_POST, handleEmergency);
  server.on("/test", HTTP_POST, handleConnectionTest);
  server.on("/status", HTTP_GET, handleStatus);
  
  server.begin();
  udp.begin(udpPort);
  
  Serial.println("ESP32 Traffic Light Controller Ready!");
  Serial.println("Phase State Format: NNNEEEWWWSSS (12 chars)");
  Serial.println("N=North(A0), E=East(C0), W=West(D0), S=South(B0)");
  Serial.println("Each direction: [Green, Yellow, Red]");
  Serial.println("Pin Mapping:");
  Serial.println("A0(North): G=26, Y=22, R=21");
  Serial.println("B0(South): G=19, Y=18, R=5");
  Serial.println("C0(East):  G=25, Y=33, R=27");
  Serial.println("D0(West):  G=12, Y=13, R=14");
  
  // Initial state - all red
  setAllRed();
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
    
    Serial.println("Received data: " + body);
    
    if (deserializeJson(doc, body) == DeserializationError::Ok) {
      
      // Filter and extract the phase state
      String phase_state = doc["phase_state"].as<String>();
      int duration = doc["duration_seconds"];
      
      // Update current state
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
      
      // Parse phase state and apply to traffic lights
      parseAndApplyPhaseState(phase_state);
      
      Serial.println("=== Phase State Filtered ===");
      Serial.println("Phase: " + phase_state);
      Serial.println("Duration: " + String(duration) + "s");
      Serial.println("============================");
      
      server.send(200, "application/json", "{\"status\":\"success\",\"phase\":\"" + phase_state + "\"}");
    } else {
      Serial.println("JSON parsing failed!");
      server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Invalid JSON\"}");
    }
  } else {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"No data received\"}");
  }
}

void handleMetrics() {
  if (server.hasArg("plain")) {
    String body = server.arg("plain");
    DynamicJsonDocument doc(1024);
    
    if (deserializeJson(doc, body) == DeserializationError::Ok) {
      JsonObject metrics = doc["metrics"];
      
      Serial.println("=== Traffic Metrics ===");
      Serial.println("A0(North): " + String(metrics["north_vehicles"].as<int>()) + " vehicles");
      Serial.println("B0(South): " + String(metrics["south_vehicles"].as<int>()) + " vehicles"); 
      Serial.println("C0(East):  " + String(metrics["east_vehicles"].as<int>()) + " vehicles");
      Serial.println("D0(West):  " + String(metrics["west_vehicles"].as<int>()) + " vehicles");
      Serial.println("======================");
      
      server.send(200, "application/json", "{\"status\":\"success\"}");
    } else {
      server.send(400, "application/json", "{\"status\":\"error\"}");
    }
  }
}

void handleEmergency() {
  if (server.hasArg("plain")) {
    String body = server.arg("plain");
    DynamicJsonDocument doc(512);
    
    if (deserializeJson(doc, body) == DeserializationError::Ok) {
      String message = doc["message"];
      String priority = doc["priority"];
      
      Serial.println("🚨 EMERGENCY: " + message + " (" + priority + ")");
      
      if (priority == "HIGH") {
        currentState.emergency = true;
        flashAllYellow(5, 200);
        soundBuzzer(5, 300);
      } else {
        soundBuzzer(2, 150);
      }
      
      server.send(200, "application/json", "{\"status\":\"emergency_handled\"}");
    }
  }
}

void handleConnectionTest() {
  Serial.println("🔗 Connection test from SUMO");
  
  // Test all directions with sample phase states
  testPhaseStates();
  
  DynamicJsonDocument response(256);
  response["status"] = "connected";
  response["device"] = "ESP32 Phase State Controller";
  response["ip"] = WiFi.localIP().toString();
  response["phase_format"] = "NNNEEEWWWSSS (12 chars)";
  
  String jsonString;
  serializeJson(response, jsonString);
  server.send(200, "application/json", jsonString);
}

void handleStatus() {
  DynamicJsonDocument status(512);
  status["current_phase"] = currentState.phaseState;
  status["duration"] = currentState.duration;
  status["emergency"] = currentState.emergency;
  status["uptime"] = millis();
  
  // Add parsed state
  JsonObject lights = status.createNestedObject("lights");
  lights["north"] = String(currentState.northLights[0] ? "G" : "") + 
                   String(currentState.northLights[1] ? "Y" : "") + 
                   String(currentState.northLights[2] ? "R" : "");
  lights["east"] = String(currentState.eastLights[0] ? "G" : "") + 
                  String(currentState.eastLights[1] ? "Y" : "") + 
                  String(currentState.eastLights[2] ? "R" : "");
  lights["west"] = String(currentState.westLights[0] ? "G" : "") + 
                  String(currentState.westLights[1] ? "Y" : "") + 
                  String(currentState.westLights[2] ? "R" : "");
  lights["south"] = String(currentState.southLights[0] ? "G" : "") + 
                   String(currentState.southLights[1] ? "Y" : "") + 
                   String(currentState.southLights[2] ? "R" : "");
  
  String jsonString;
  serializeJson(status, jsonString);
  server.send(200, "application/json", jsonString);
}

void handleUDPMessages() {
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char buffer[256];
    int len = udp.read(buffer, sizeof(buffer) - 1);
    buffer[len] = '\0';
    
    DynamicJsonDocument doc(256);
    if (deserializeJson(doc, buffer) == DeserializationError::Ok) {
      String phase = doc["phase"].as<String>();
      
      if (phase.length() == 12) {
        currentState.phaseState = phase;
        parseAndApplyPhaseState(phase);
        Serial.println("📡 UDP Phase: " + phase);
      }
    }
  }
}

void parseAndApplyPhaseState(String phaseState) {
  if (phaseState.length() != 12) {
    Serial.println("❌ Invalid phase state length: " + String(phaseState.length()));
    setAllRed();
    return;
  }
  
  Serial.println("🔍 Parsing phase state: " + phaseState);
  
  // Parse each direction (3 characters each)
  // Characters 0-2: North (A0)
  currentState.northLights[0] = (phaseState.charAt(0) == 'G');  // Green
  currentState.northLights[1] = (phaseState.charAt(1) == 'Y');  // Yellow
  currentState.northLights[2] = (phaseState.charAt(2) == 'r');  // Red
  
  // Characters 3-5: East (C0)
  currentState.eastLights[0] = (phaseState.charAt(3) == 'G');   // Green
  currentState.eastLights[1] = (phaseState.charAt(4) == 'Y');   // Yellow
  currentState.eastLights[2] = (phaseState.charAt(5) == 'r');   // Red
  
  // Characters 6-8: West (D0)
  currentState.westLights[0] = (phaseState.charAt(6) == 'G');   // Green
  currentState.westLights[1] = (phaseState.charAt(7) == 'Y');   // Yellow
  currentState.westLights[2] = (phaseState.charAt(8) == 'r');   // Red
  
  // Characters 9-11: South (B0)
  currentState.southLights[0] = (phaseState.charAt(9) == 'G');  // Green
  currentState.southLights[1] = (phaseState.charAt(10) == 'Y'); // Yellow
  currentState.southLights[2] = (phaseState.charAt(11) == 'r'); // Red
  
  // Apply to physical LEDs
  applyParsedStateToLEDs();
  
  // Print parsed state
  printParsedState();
}

void applyParsedStateToLEDs() {
  // Apply North (A0) lights
  digitalWrite(A0_GREEN, currentState.northLights[0] ? HIGH : LOW);
  digitalWrite(A0_YELLOW, currentState.northLights[1] ? HIGH : LOW);
  digitalWrite(A0_RED, currentState.northLights[2] ? HIGH : LOW);
  
  // Apply East (C0) lights
  digitalWrite(C0_GREEN, currentState.eastLights[0] ? HIGH : LOW);
  digitalWrite(C0_YELLOW, currentState.eastLights[1] ? HIGH : LOW);
  digitalWrite(C0_RED, currentState.eastLights[2] ? HIGH : LOW);
  
  // Apply West (D0) lights
  digitalWrite(D0_GREEN, currentState.westLights[0] ? HIGH : LOW);
  digitalWrite(D0_YELLOW, currentState.westLights[1] ? HIGH : LOW);
  digitalWrite(D0_RED, currentState.westLights[2] ? HIGH : LOW);
  
  // Apply South (B0) lights
  digitalWrite(B0_GREEN, currentState.southLights[0] ? HIGH : LOW);
  digitalWrite(B0_YELLOW, currentState.southLights[1] ? HIGH : LOW);
  digitalWrite(B0_RED, currentState.southLights[2] ? HIGH : LOW);
}

void printParsedState() {
  Serial.println("🚦 Traffic Light States:");
  
  // North (A0)
  String northState = "";
  if (currentState.northLights[0]) northState += "GREEN ";
  if (currentState.northLights[1]) northState += "YELLOW ";
  if (currentState.northLights[2]) northState += "RED ";
  if (northState == "") northState = "OFF";
  Serial.println("A0(North): " + northState + " - Pins G=26(" + (currentState.northLights[0] ? "ON" : "OFF") + 
                 "), Y=22(" + (currentState.northLights[1] ? "ON" : "OFF") + 
                 "), R=21(" + (currentState.northLights[2] ? "ON" : "OFF") + ")");
  
  // East (C0)
  String eastState = "";
  if (currentState.eastLights[0]) eastState += "GREEN ";
  if (currentState.eastLights[1]) eastState += "YELLOW ";
  if (currentState.eastLights[2]) eastState += "RED ";
  if (eastState == "") eastState = "OFF";
  Serial.println("C0(East):  " + eastState + " - Pins G=25(" + (currentState.eastLights[0] ? "ON" : "OFF") + 
                 "), Y=33(" + (currentState.eastLights[1] ? "ON" : "OFF") + 
                 "), R=27(" + (currentState.eastLights[2] ? "ON" : "OFF") + ")");
  
  // West (D0)
  String westState = "";
  if (currentState.westLights[0]) westState += "GREEN ";
  if (currentState.westLights[1]) westState += "YELLOW ";
  if (currentState.westLights[2]) westState += "RED ";
  if (westState == "") westState = "OFF";
  Serial.println("D0(West):  " + westState + " - Pins G=12(" + (currentState.westLights[0] ? "ON" : "OFF") + 
                 "), Y=13(" + (currentState.westLights[1] ? "ON" : "OFF") + 
                 "), R=14(" + (currentState.westLights[2] ? "ON" : "OFF") + ")");
  
  // South (B0)
  String southState = "";
  if (currentState.southLights[0]) southState += "GREEN ";
  if (currentState.southLights[1]) southState += "YELLOW ";
  if (currentState.southLights[2]) southState += "RED ";
  if (southState == "") southState = "OFF";
  Serial.println("B0(South): " + southState + " - Pins G=19(" + (currentState.southLights[0] ? "ON" : "OFF") + 
                 "), Y=18(" + (currentState.southLights[1] ? "ON" : "OFF") + 
                 "), R=5(" + (currentState.southLights[2] ? "ON" : "OFF") + ")");
}

void setAllRed() {
  // Set all directions to RED
  digitalWrite(A0_GREEN, LOW);  digitalWrite(A0_YELLOW, LOW);  digitalWrite(A0_RED, HIGH);
  digitalWrite(B0_GREEN, LOW);  digitalWrite(B0_YELLOW, LOW);  digitalWrite(B0_RED, HIGH);
  digitalWrite(C0_GREEN, LOW);  digitalWrite(C0_YELLOW, LOW);  digitalWrite(C0_RED, HIGH);
  digitalWrite(D0_GREEN, LOW);  digitalWrite(D0_YELLOW, LOW);  digitalWrite(D0_RED, HIGH);
  
  // Update state
  for (int i = 0; i < 3; i++) {
    currentState.northLights[i] = (i == 2);  // Only red ON
    currentState.eastLights[i] = (i == 2);
    currentState.westLights[i] = (i == 2);
    currentState.southLights[i] = (i == 2);
  }
  
  currentState.phaseState = "rrrrrrrrrrrr";
  currentState.emergency = false;
  
  Serial.println("🔴 All directions set to RED");
}

void flashAllYellow(int count, int delayMs) {
  for (int i = 0; i < count; i++) {
    // Turn on all yellows
    digitalWrite(A0_YELLOW, HIGH);
    digitalWrite(B0_YELLOW, HIGH);
    digitalWrite(C0_YELLOW, HIGH);
    digitalWrite(D0_YELLOW, HIGH);
    delay(delayMs);
    
    // Turn off all yellows  
    digitalWrite(A0_YELLOW, LOW);
    digitalWrite(B0_YELLOW, LOW);
    digitalWrite(C0_YELLOW, LOW);
    digitalWrite(D0_YELLOW, LOW);
    delay(delayMs);
  }
  
  // Return to previous state
  applyParsedStateToLEDs();
}

void testPhaseStates() {
  Serial.println("🧪 Testing phase states...");
  
  String testPhases[] = {
    "GGGrrrrrrrrr",  // North Green
    "rrrGGGrrrrrr",  // East Green
    "rrrrrGGGrrrr",  // West Green
    "rrrrrrrrrGGG",  // South Green
    "rYrrrrrrrrrr",  // North Yellow
    "rrrrrrrrrrrr"   // All Red
  };
  
  String descriptions[] = {
    "North Green", "East Green", "West Green", 
    "South Green", "North Yellow", "All Red"
  };
  
  for (int i = 0; i < 6; i++) {
    Serial.println("Testing: " + descriptions[i] + " (" + testPhases[i] + ")");
    parseAndApplyPhaseState(testPhases[i]);
    delay(1000);
  }
  
  setAllRed();
  Serial.println("✅ Phase state test complete");
}

void blinkEmergencyPattern() {
  static unsigned long lastBlink = 0;
  static bool blinkState = false;
  
  if (millis() - lastBlink > 500) {
    blinkState = !blinkState;
    
    // Blink all yellow LEDs during emergency
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