/*
  Grove 2-Channel SPDT Relay test.

  Wiring:
    SIG1 -> Arduino D7 -> discharge relay
    SIG2 -> Arduino D8 -> charge relay

  Logic:
    Grove relay input HIGH = relay active
    Grove relay input LOW  = relay inactive
*/

const byte DISCHARGE_PIN = 7;
const byte CHARGE_PIN = 8;

enum RelayMode {
  MODE_OFF,
  MODE_CHARGE,
  MODE_DISCHARGE
};

RelayMode currentMode = MODE_OFF;

void setRelayMode(RelayMode mode);
void toggleRelayMode();
void printRelayMode();

void setup() {
  Serial.begin(9600);

  pinMode(DISCHARGE_PIN, OUTPUT);
  pinMode(CHARGE_PIN, OUTPUT);
  setRelayMode(MODE_OFF);

  Serial.println("Grove relay test ready.");
  Serial.println("Type: charge, discharge, off, toggle, read");
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toLowerCase();

  if (cmd == "charge") {
    setRelayMode(MODE_CHARGE);
  } else if (cmd == "discharge") {
    setRelayMode(MODE_DISCHARGE);
  } else if (cmd == "off") {
    setRelayMode(MODE_OFF);
  } else if (cmd == "toggle") {
    toggleRelayMode();
  } else if (cmd == "read") {
    printRelayMode();
  } else {
    Serial.println("Unknown command. Use: charge, discharge, off, toggle, read");
  }
}

void setRelayMode(RelayMode mode) {
  if (mode == MODE_CHARGE) {
    digitalWrite(DISCHARGE_PIN, LOW);
    digitalWrite(CHARGE_PIN, HIGH);
  } else if (mode == MODE_DISCHARGE) {
    digitalWrite(CHARGE_PIN, LOW);
    digitalWrite(DISCHARGE_PIN, HIGH);
  } else {
    digitalWrite(CHARGE_PIN, LOW);
    digitalWrite(DISCHARGE_PIN, LOW);
  }

  currentMode = mode;
  printRelayMode();
}

void toggleRelayMode() {
  if (currentMode == MODE_CHARGE) {
    setRelayMode(MODE_DISCHARGE);
  } else if (currentMode == MODE_DISCHARGE) {
    setRelayMode(MODE_OFF);
  } else {
    setRelayMode(MODE_CHARGE);
  }
}

void printRelayMode() {
  Serial.print("Charge D8 = ");
  Serial.print(digitalRead(CHARGE_PIN) == HIGH ? "HIGH" : "LOW");
  Serial.print(" | Discharge D7 = ");
  Serial.print(digitalRead(DISCHARGE_PIN) == HIGH ? "HIGH" : "LOW");
  Serial.print(" | Mode = ");

  if (currentMode == MODE_CHARGE) {
    Serial.println("charge");
  } else if (currentMode == MODE_DISCHARGE) {
    Serial.println("discharge");
  } else {
    Serial.println("off");
  }
}
