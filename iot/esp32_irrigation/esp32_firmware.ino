/*
 * ====================================================================
 * AgriSmart Connect - ESP32 Smart Irrigation System Firmware
 * ====================================================================
 * Hardware Components:
 *  - ESP32 Development Board
 *  - Capacitive Soil Moisture Sensor v1.2 (Analog Pin 34)
 *  - 5V Relay Module / MOSFET Driver (Digital Output Pin 23)
 *  - DC Water Pump / AC Motor Contactor Interface
 *  - 3.3V / 5V Regulated Power Supply
 *
 * Architecture:
 *  Field Soil -> Capacitive Sensor -> ESP32 ADC -> Wi-Fi -> Flask REST API
 *  Endpoint: http://<server-ip>:5000/api/iot/telemetry
 *
 * IMPORTANT ELECTRICAL SAFETY NOTICE:
 *  For high-power AC agricultural motors (1HP - 10HP), NEVER directly 
 *  switch motor mains using a standard hobby blue relay module.
 *  Always drive an appropriately rated electromagnetic CONTACTOR with 
 *  thermal overload relay protection and snubber circuitry.
 * ====================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>

// Wi-Fi Configuration
const char* WIFI_SSID = "kaushal";
const char* WIFI_PASS = "123456777";

// AgriSmart Connect Backend Server
// Replace with your Laptop / Server IP on local Wi-Fi (e.g. 192.168.1.5)
const char* SERVER_URL = "http://10.91.137.25:5000/api/iot/telemetry";

// Pin Definitions
const int SENSOR_PIN = 34;    // Analog pin for Capacitive Moisture Sensor
const int RELAY_PIN  = 23;    // Digital pin to trigger Relay / Contactor
const int STATUS_LED = 2;     // Built-in ESP32 LED

// Calibration Values (Adjust for your specific soil & sensor):
// Air Reading (completely dry) ~ 3200
// Water Reading (submerged)    ~ 1400
const int DRY_ADC_VALUE = 3200;
const int WET_ADC_VALUE = 1400;

// Threshold: Irrigation triggers below 35% in automatic mode
const float MOISTURE_THRESHOLD_PCT = 35.0;

// Timing interval (Send telemetry every 15 seconds)
unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL_MS = 15000;

bool pumpRunning = false;
String operatingMode = "AUTO";

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=============================================");
  Serial.println(" AgriSmart Connect - ESP32 Smart Irrigation");
  Serial.println("=============================================");

  pinMode(SENSOR_PIN, INPUT);
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(STATUS_LED, OUTPUT);

  // Default: Pump OFF (Relays are typically active LOW or HIGH depending on module)
  digitalWrite(RELAY_PIN, LOW);
  digitalWrite(STATUS_LED, LOW);

  // Connect to Wi-Fi
  connectWiFi();
}

void loop() {
  // Reconnect Wi-Fi if dropped
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  // Read Soil Moisture
  int rawADC = analogRead(SENSOR_PIN);
  float moisturePct = calculateMoisturePercentage(rawADC);

  // Automatic Irrigation Control Logic
  if (operatingMode == "AUTO") {
    if (moisturePct < MOISTURE_THRESHOLD_PCT && !pumpRunning) {
      Serial.println("[AUTO] Soil is dry (< 35%). Activating irrigation pump...");
      setPumpState(true);
    } else if (moisturePct >= 65.0 && pumpRunning) {
      Serial.println("[AUTO] Optimal saturation reached (>= 65%). Turning pump OFF...");
      setPumpState(false);
    }
  }

  // Send Telemetry to AgriSmart Connect Flask API
  if (millis() - lastSendTime >= SEND_INTERVAL_MS) {
    lastSendTime = millis();
    sendTelemetryToServer(moisturePct, pumpRunning);
  }

  delay(500);
}

// Convert Raw ADC reading into Calibrated 0% - 100% Moisture
float calculateMoisturePercentage(int raw) {
  raw = constrain(raw, WET_ADC_VALUE, DRY_ADC_VALUE);
  float pct = map(raw, DRY_ADC_VALUE, WET_ADC_VALUE, 0, 100);
  return constrain(pct, 0.0, 100.0);
}

// Toggle Relay / Contactor
void setPumpState(bool turnOn) {
  pumpRunning = turnOn;
  digitalWrite(RELAY_PIN, turnOn ? HIGH : LOW);
  digitalWrite(STATUS_LED, turnOn ? HIGH : LOW);
  Serial.printf("[HARDWARE] Pump state changed to: %s\n", turnOn ? "ON" : "OFF");
}

// Wi-Fi Connection
void connectWiFi() {
  Serial.printf("[Wi-Fi] Connecting to '%s'...", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 25) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[Wi-Fi] Connected! IP Address: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[Wi-Fi] Connection timed out. Running in standalone fallback mode.");
  }
}

// HTTP POST Telemetry to Flask Backend
void sendTelemetryToServer(float moisturePct, bool isPumpOn) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  // Construct JSON Payload
  String payload = "{\"device_id\":\"ESP32-FIELD-01\",\"moisture_pct\":" + String(moisturePct, 1) +
                   ",\"temperature_c\":28.5,\"pump_status\":\"" + (isPumpOn ? "ON" : "OFF") + "\"}";

  Serial.printf("[HTTP] POST %s -> %s\n", SERVER_URL, payload.c_str());
  int httpCode = http.POST(payload);

  if (httpCode > 0) {
    String response = http.getString();
    Serial.printf("[HTTP] Response (%d): %s\n", httpCode, response.c_str());

    // Check if server commanded manual pump override (supports both spaced and compact JSON)
    bool cmdOn = (response.indexOf("\"pump_status\":\"ON\"") >= 0 || response.indexOf("\"pump_status\": \"ON\"") >= 0);
    bool cmdOff = (response.indexOf("\"pump_status\":\"OFF\"") >= 0 || response.indexOf("\"pump_status\": \"OFF\"") >= 0);

    if (cmdOn && !pumpRunning) {
      Serial.println("[COMMAND] Server requested: TURN PUMP ON");
      setPumpState(true);
    } else if (cmdOff && pumpRunning) {
      Serial.println("[COMMAND] Server requested: TURN PUMP OFF");
      setPumpState(false);
    }

    if (response.indexOf("\"mode\":\"MANUAL\"") >= 0 || response.indexOf("\"mode\": \"MANUAL\"") >= 0) {
      operatingMode = "MANUAL";
    } else if (response.indexOf("\"mode\":\"AUTO\"") >= 0 || response.indexOf("\"mode\": \"AUTO\"") >= 0) {
      operatingMode = "AUTO";
    }
  } else {
    Serial.printf("[HTTP] Failed, error: %s\n", http.errorToString(httpCode).c_str());
  }

  http.end();
}
