/*
  Relay test for your exact schematic.

  Schematic:
    D10 -> Q3 gate -> relay SET coil, relay pin 1
    D11 -> Q2 gate -> relay RESET coil, relay pin 6
    A0  -> relay output/contact sense

  Logic:
    P-MOSFET ON  = Arduino pin LOW
    P-MOSFET OFF = Arduino pin HIGH
*/

const byte SET_PIN   = 3;   // D10, Q3, relay SET
const byte RESET_PIN = 2;   // D11, Q2, relay RESET
const byte SENSE_PIN = A0;

const unsigned long PULSE_MS = 200;

void setup() {
  Serial.begin(9600);

  pinMode(SET_PIN, OUTPUT);
  pinMode(RESET_PIN, OUTPUT);

  // OFF state for P-MOSFETs
  digitalWrite(SET_PIN, HIGH);
  digitalWrite(RESET_PIN, HIGH);

  delay(500);

  Serial.println("Relay test ready.");
  Serial.println("Type: on, off, toggle, read");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toLowerCase();

    if (cmd == "on") {
      relaySet();
    }
    else if (cmd == "off") {
      relayReset();
    }
    else if (cmd == "toggle") {
      relaySet();
      delay(1000);
      relayReset();
    }
    else if (cmd == "read") {
      readA0();
    }
    else {
      Serial.println("Unknown command. Use: on, off, toggle, read");
    }
  }

  static unsigned long lastRead = 0;
  if (millis() - lastRead >= 1000) {
    lastRead = millis();
    readA0();
  }
}

void relaySet() {
  Serial.println("SET / ON pulse");

  digitalWrite(RESET_PIN, HIGH);  // make sure reset is off
  delay(5);

  digitalWrite(SET_PIN, LOW);     // P-MOS ON
  delay(PULSE_MS);
  digitalWrite(SET_PIN, HIGH);    // P-MOS OFF

  delay(50);
  readA0();
}

void relayReset() {
  Serial.println("RESET / OFF pulse");

  digitalWrite(SET_PIN, HIGH);    // make sure set is off
  delay(5);

  digitalWrite(RESET_PIN, LOW);   // P-MOS ON
  delay(PULSE_MS);
  digitalWrite(RESET_PIN, HIGH);  // P-MOS OFF

  delay(50);
  readA0();
}

void readA0() {
  int raw = analogRead(SENSE_PIN);
  float voltage = raw * 5.0 / 1023.0;

  Serial.print("A0 raw = ");
  Serial.print(raw);
  Serial.print("   voltage = ");
  Serial.print(voltage, 3);
  Serial.println(" V");
}