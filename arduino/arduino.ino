#include <math.h>

/*
 * ========================================================================
 * Battery Tester Arduino Controller - 4S4P / ACS712
 * ========================================================================
 * Inputs:
 *   A1-A4 = cumulative 1S-4S battery taps
 *   A5    = temperature sensor (LM35-compatible, 10 mV/degree C)
 *   A0    = ACS712 current sensor
 *
 * Outputs:
 *   D7 = Grove relay SIG1, discharge relay, active HIGH
 *   D8 = Grove relay SIG2, charge relay, active HIGH
 *
 * Runtime configuration accepted from Python:
 *   CMIN, CMAX, ENDC, VREFI, VREFA, SAMP, ADCS
 *
 * Charge stop packets:
 *   MAX = maximum cell-voltage cutoff
 *   END = charge-end current confirmed near maximum cell voltage
 *
 * Last Updated: 01/05/2026
 * ========================================================================
 */

// ========================================================================
// RUNTIME CONFIGURATION DEFAULTS
// ========================================================================

const byte SERIES_CELLS = 4;
const float ADC_COUNTS = 1024.0;

// Voltage reference calibration
float idleVRef = 4.94;    // Measured 5V rail with relays off
float activeVRef = 4.90;  // Measured 5V rail while charge/discharge relay is active

// Per-cell safety limits
float cellMaxVoltage = 4.20;  // Maximum safe cell voltage
float cellMinVoltage = 2.50;  // Minimum safe cell voltage

// Voltage divider resistor values in kOhm.
// R1 = resistor from battery tap to ADC input.
// R2 = resistor from ADC input to GND.
//
// B1 is direct through 1k, with a capacitor to GND for filtering.
// Represent that as R1 = 0k and R2 = 1k so its multiplier is 1.
const float voltageDividerR1[SERIES_CELLS] = {
  0.00f,   // B1 direct with 1k + C1
  6.74f,   // B2
  17.80f,  // B3
  26.90f   // B4
};

const float voltageDividerR2[SERIES_CELLS] = {
  1.00f,  // B1 direct reference
  9.74f,  // B2
  9.86f,  // B3
  9.81f   // B4
};

float voltageDividerMultiplier[SERIES_CELLS];

void calculateVoltageDividerMultipliers() {
  for (uint8_t i = 0; i < SERIES_CELLS; i++) {
    voltageDividerMultiplier[i] =
      (voltageDividerR1[i] + voltageDividerR2[i]) / voltageDividerR2[i];
  }
}

// Current sensor configuration for ACS712.
// 30A = 0.066 V/A.
float currentSensitivity = 0.066;
int currentOffsetRaw = 512;
float chargeEndCurrentA = 0.05;
const float CHARGE_END_VOLTAGE_MARGIN = 0.10;
const byte CHARGE_END_CONFIRM_SAMPLES = 3;

// Timing configuration
unsigned long samplingPeriodMs = 500;
int adcSamples = 8;

// ========================================================================
// PIN DEFINITIONS
// ========================================================================

const uint8_t PIN_TAP[SERIES_CELLS] = {A1, A2, A3, A4};
const uint8_t PIN_TEMPERATURE = A5;
const uint8_t PIN_CURRENT = A0;
const uint8_t PIN_RELAY_DISCHARGE = 7;  // Grove SIG1
const uint8_t PIN_RELAY_CHARGE = 8;     // Grove SIG2

// ========================================================================
// STATE MACHINE DEFINITION
// ========================================================================

typedef enum {
  STATE_OFF,
  STATE_CALIBRATION,
  STATE_IDLE,
  STATE_CHARGE,
  STATE_DISCHARGE,
  STATE_RESTING
} SystemState;

// ========================================================================
// GLOBAL VARIABLES
// ========================================================================

SystemState currentState = STATE_OFF;
bool readingEnabled = false;

float tapVoltage[SERIES_CELLS] = {0.0, 0.0, 0.0, 0.0};
float cellVoltage[SERIES_CELLS] = {0.0, 0.0, 0.0, 0.0};
float packVoltage = 0.0;
float currentA = 0.0;
float temperatureC = 0.0;
bool newDataAvailable = false;
byte lowChargeCurrentSamples = 0;

unsigned long currentTime = 0;
unsigned long lastSampleTime = 0;

void enableChargeRelay();
void enableDischargeRelay();
void makeSafeIdle();

// ========================================================================
// SETUP
// ========================================================================

void setup() {
  Serial.begin(9600);
  calculateVoltageDividerMultipliers();

  pinMode(PIN_RELAY_DISCHARGE, OUTPUT);
  pinMode(PIN_RELAY_CHARGE, OUTPUT);
  makeSafeIdle();

  for (byte i = 0; i < SERIES_CELLS; i++) {
    pinMode(PIN_TAP[i], INPUT);
  }
  pinMode(PIN_CURRENT, INPUT);
  pinMode(PIN_TEMPERATURE, INPUT);

  analogReference(DEFAULT);

  lastSampleTime = millis();
  delay(100);
}

// ========================================================================
// RELAY / LOAD CONTROL
// ========================================================================

void enableChargeRelay() {
  digitalWrite(PIN_RELAY_DISCHARGE, LOW);
  digitalWrite(PIN_RELAY_CHARGE, HIGH);
}

void enableDischargeRelay() {
  digitalWrite(PIN_RELAY_CHARGE, LOW);
  digitalWrite(PIN_RELAY_DISCHARGE, HIGH);
}

void makeSafeIdle() {
  digitalWrite(PIN_RELAY_CHARGE, LOW);
  digitalWrite(PIN_RELAY_DISCHARGE, LOW);
}

// ========================================================================
// ANALOG READING
// ========================================================================

int stableAnalogRead(uint8_t pin) {
  analogRead(pin);
  delayMicroseconds(100);

  long sum = 0;
  int samples = adcSamples;
  if (samples < 1) {
    samples = 1;
  }
  if (samples > 64) {
    samples = 64;
  }

  for (int i = 0; i < samples; i++) {
    sum += analogRead(pin);
    delayMicroseconds(50);
  }

  return (int)(sum / samples);
}

float selectedVRef() {
  if (currentState == STATE_CHARGE || currentState == STATE_DISCHARGE) {
    return activeVRef;
  }
  return idleVRef;
}

float adcToVoltage(int raw, float referenceVoltage) {
  return (raw * referenceVoltage) / ADC_COUNTS;
}

void deriveCellVoltages() {
  cellVoltage[0] = tapVoltage[0];
  for (byte i = 1; i < SERIES_CELLS; i++) {
    cellVoltage[i] = tapVoltage[i] - tapVoltage[i - 1];
  }
  packVoltage = tapVoltage[SERIES_CELLS - 1];
}

void readSensors() {
  if (!readingEnabled || newDataAvailable) {
    return;
  }

  float referenceVoltage = selectedVRef();

  for (byte i = 0; i < SERIES_CELLS; i++) {
    int rawTap = stableAnalogRead(PIN_TAP[i]);
    tapVoltage[i] = adcToVoltage(rawTap, referenceVoltage) * voltageDividerMultiplier[i];
    delay(5);
  }
  deriveCellVoltages();

  int rawCurrent = stableAnalogRead(PIN_CURRENT);
  currentA = ((rawCurrent - currentOffsetRaw) * (referenceVoltage / ADC_COUNTS)) / currentSensitivity;
  delay(5);

  int rawTemp = stableAnalogRead(PIN_TEMPERATURE);
  temperatureC = adcToVoltage(rawTemp, referenceVoltage) / 0.01;  // LM35-compatible 10 mV/°C

  newDataAvailable = true;
}

// ========================================================================
// PACKET COMMUNICATION
// ========================================================================

void sendValue(const String& code, float value) {
  char valueStr[24];
  dtostrf(value, 0, 8, valueStr);
  Serial.print(code);
  Serial.print(";");
  Serial.print(valueStr);
  Serial.println(";1");
}

String getConfigKey(const String& command) {
  int first = command.indexOf(';');
  int second = command.indexOf(';', first + 1);
  if (first < 0 || second < 0) {
    return "";
  }
  return command.substring(first + 1, second);
}

String getConfigValue(const String& command) {
  int first = command.indexOf(';');
  int second = command.indexOf(';', first + 1);
  if (first < 0 || second < 0) {
    return "";
  }
  return command.substring(second + 1);
}

void applyConfig(const String& key, const String& valueText) {
  float value = valueText.toFloat();

  if (key == "CMIN") {
    cellMinVoltage = value;
  } else if (key == "CMAX") {
    cellMaxVoltage = value;
  } else if (key == "ENDC") {
    chargeEndCurrentA = value;
  } else if (key == "VREFI") {
    if (value >= 3.0f && value <= 5.5f) {
      idleVRef = value;
    }
  } else if (key == "VREFA") {
    if (value >= 3.0f && value <= 5.5f) {
      activeVRef = value;
    }
  } else if (key == "VREF") {
    if (value >= 3.0f && value <= 5.5f) {
      idleVRef = value;
      activeVRef = value;
    }
  } else if (key == "SAMP") {
    long parsed = valueText.toInt();
    if (parsed >= 50 && parsed <= 60000) {
      samplingPeriodMs = parsed;
    }
  } else if (key == "ADCS") {
    int parsed = valueText.toInt();
    if (parsed >= 1 && parsed <= 64) {
      adcSamples = parsed;
    }
  }
}

void processCommand() {
  if (!Serial.available()) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();

  if (command.length() == 0) {
    return;
  }

  if (command.startsWith("CFG;")) {
    String key = getConfigKey(command);
    String valueText = getConfigValue(command);
    if (key.length() > 0 && valueText.length() > 0) {
      applyConfig(key, valueText);
    }
    return;
  }

  if (command == "CSC") {
    readingEnabled = true;
    makeSafeIdle();
    currentState = STATE_CALIBRATION;
    delay(100);
  }

  else if (command == "IDL") {
    readingEnabled = true;
    makeSafeIdle();
    currentState = STATE_IDLE;
    delay(100);
  }

  else if (command == "STC") {
    readingEnabled = true;
    enableChargeRelay();
    lowChargeCurrentSamples = 0;
    currentState = STATE_CHARGE;
    delay(100);
  }

  else if (command == "SPC") {
    readingEnabled = true;
    makeSafeIdle();
    currentState = STATE_RESTING;
    delay(100);
  }

  else if (command == "STD") {
    readingEnabled = true;
    enableDischargeRelay();
    currentState = STATE_DISCHARGE;
    delay(100);
  }

  else if (command == "SPD") {
    readingEnabled = true;
    makeSafeIdle();
    currentState = STATE_RESTING;
    delay(100);
  }

  else if (command == "CLS" || command == "OFF") {
    readingEnabled = false;
    makeSafeIdle();
    currentState = STATE_OFF;
    delay(100);
  }
}

// ========================================================================
// TELEMETRY AND SAFETY
// ========================================================================

float minCellVoltage() {
  float minValue = cellVoltage[0];
  for (byte i = 1; i < SERIES_CELLS; i++) {
    if (cellVoltage[i] < minValue) {
      minValue = cellVoltage[i];
    }
  }
  return minValue;
}

float maxCellVoltage() {
  float maxValue = cellVoltage[0];
  for (byte i = 1; i < SERIES_CELLS; i++) {
    if (cellVoltage[i] > maxValue) {
      maxValue = cellVoltage[i];
    }
  }
  return maxValue;
}

void sendTelemetry(bool includeElapsedTick) {
  sendValue("VVV", packVoltage);

  for (byte i = 0; i < SERIES_CELLS; i++) {
    char code[4];
    snprintf(code, sizeof(code), "C%02d", i + 1);
    sendValue(String(code), cellVoltage[i]);
  }

  for (byte i = 0; i < SERIES_CELLS; i++) {
    char code[4];
    snprintf(code, sizeof(code), "S%02d", i + 1);
    sendValue(String(code), tapVoltage[i]);
  }

  // Send signed current so the Python-side calibration offset can be applied
  // before the GUI converts the corrected value to an absolute display value.
  sendValue("III", currentA);
  sendValue("TTT", temperatureC);

  if (includeElapsedTick) {
    sendValue("DDD", 0.0);
  }
}

void stopForMaximumCellVoltage() {
  makeSafeIdle();
  currentState = STATE_OFF;
  readingEnabled = false;
  sendValue("MAX", maxCellVoltage());
}

void stopForChargeEndCurrent() {
  makeSafeIdle();
  currentState = STATE_OFF;
  readingEnabled = false;
  sendValue("END", fabs(currentA));
}

void stopForMinimumCellVoltage() {
  makeSafeIdle();
  currentState = STATE_OFF;
  readingEnabled = false;
  sendValue("MIN", minCellVoltage());
}

// ========================================================================
// STATE HANDLERS
// ========================================================================

void handleOffState() {
  delay(100);
}

void handleIdleState() {
  if (newDataAvailable) {
    sendTelemetry(false);
    newDataAvailable = false;
  }
}

void handleCalibrationState() {
  if (newDataAvailable) {
    sendValue("III", currentA);
    newDataAvailable = false;
  }
}

void handleChargeState() {
  if (newDataAvailable) {
    sendTelemetry(true);
    newDataAvailable = false;

    float maximumCellVoltage = maxCellVoltage();
    if (maximumCellVoltage >= cellMaxVoltage) {
      lowChargeCurrentSamples = 0;
      stopForMaximumCellVoltage();
    } else if (
      maximumCellVoltage >= cellMaxVoltage - CHARGE_END_VOLTAGE_MARGIN
      && fabs(currentA) < chargeEndCurrentA
    ) {
      if (lowChargeCurrentSamples < CHARGE_END_CONFIRM_SAMPLES) {
        lowChargeCurrentSamples++;
      }
      if (lowChargeCurrentSamples >= CHARGE_END_CONFIRM_SAMPLES) {
        stopForChargeEndCurrent();
      }
    } else {
      lowChargeCurrentSamples = 0;
    }
  }
}

void handleDischargeState() {
  if (newDataAvailable) {
    sendTelemetry(true);
    newDataAvailable = false;

    if (minCellVoltage() <= cellMinVoltage) {
      stopForMinimumCellVoltage();
    }
  }
}

void handleRestingState() {
  if (newDataAvailable) {
    sendTelemetry(true);
    newDataAvailable = false;
  }
}

// ========================================================================
// MAIN LOOP
// ========================================================================

void loop() {
  processCommand();

  currentTime = millis();
  if ((currentTime - lastSampleTime) >= samplingPeriodMs) {
    if (readingEnabled && !newDataAvailable) {
      readSensors();
    }
    lastSampleTime = currentTime;
  }

  switch (currentState) {
    case STATE_OFF:
      handleOffState();
      break;

    case STATE_IDLE:
      handleIdleState();
      break;

    case STATE_CALIBRATION:
      handleCalibrationState();
      break;

    case STATE_CHARGE:
      handleChargeState();
      break;

    case STATE_DISCHARGE:
      handleDischargeState();
      break;

    case STATE_RESTING:
      handleRestingState();
      break;

    default:
      currentState = STATE_OFF;
      readingEnabled = false;
      makeSafeIdle();
      break;
  }
}
