#include <SPI.h>
#include <Wire.h>
#include <mcp2515.h>

// ===================== USER SETTINGS =====================
#define CAN_CS_PIN 10

#define LIDAR_I2C_ADDR 0x62

#define CAN_SPEED CAN_500KBPS
#define MCP_CLOCK MCP_8MHZ

#define CAN_ID_SAFETY_CMD 0x120

#define NORMAL_DISTANCE_CM    100
#define WARNING_DISTANCE_CM   50

#define SPEED_NORMAL    180
#define SPEED_WARNING   80
#define SPEED_EMERGENCY 0
// =========================================================

#define STATE_NORMAL    0
#define STATE_WARNING   1
#define STATE_EMERGENCY 2

MCP2515 mcp2515(CAN_CS_PIN);
struct can_frame txMsg;

uint8_t messageCounter = 0;

uint16_t readLidarDistanceCm() {
  Wire.beginTransmission(LIDAR_I2C_ADDR);
  Wire.write(0x00);
  Wire.write(0x04);
  if (Wire.endTransmission() != 0) {
    return 999;
  }

  delay(20);

  Wire.beginTransmission(LIDAR_I2C_ADDR);
  Wire.write(0x0F);
  if (Wire.endTransmission(false) != 0) {
    return 999;
  }

  Wire.requestFrom(LIDAR_I2C_ADDR, 2);

  if (Wire.available() < 2) {
    return 999;
  }

  uint8_t highByte = Wire.read();
  uint8_t lowByte = Wire.read();

  uint16_t distance = ((uint16_t)highByte << 8) | lowByte;
  return distance;
}

uint8_t calculateChecksum(uint8_t state, uint8_t speed, uint8_t brake, uint16_t distanceCm, uint8_t counter) {
  uint8_t dLow = distanceCm & 0xFF;
  uint8_t dHigh = (distanceCm >> 8) & 0xFF;

  return state ^ speed ^ brake ^ dLow ^ dHigh ^ counter;
}

void sendSafetyCommand(uint8_t state, uint8_t speed, uint8_t brake, uint16_t distanceCm) {
  txMsg.can_id = CAN_ID_SAFETY_CMD;
  txMsg.can_dlc = 7;

  txMsg.data[0] = state;
  txMsg.data[1] = speed;
  txMsg.data[2] = brake;
  txMsg.data[3] = distanceCm & 0xFF;
  txMsg.data[4] = (distanceCm >> 8) & 0xFF;
  txMsg.data[5] = messageCounter;
  txMsg.data[6] = calculateChecksum(state, speed, brake, distanceCm, messageCounter);

  mcp2515.sendMessage(&txMsg);

  messageCounter++;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin();
  SPI.begin();

  mcp2515.reset();
  mcp2515.setBitrate(CAN_SPEED, MCP_CLOCK);
  mcp2515.setNormalMode();

  Serial.println("====================================");
  Serial.println("STM32 Safety Supervisor ECU Started");
  Serial.println("LIDAR + CAN MCP2515 8MHz");
  Serial.println("====================================");
}

void loop() {
  uint16_t distanceCm = readLidarDistanceCm();

  uint8_t state;
  uint8_t speed;
  uint8_t brake;

  if (distanceCm <= WARNING_DISTANCE_CM) {
    state = STATE_EMERGENCY;
    speed = SPEED_EMERGENCY;
    brake = 1;
  }
  else if (distanceCm <= NORMAL_DISTANCE_CM) {
    state = STATE_WARNING;
    speed = SPEED_WARNING;
    brake = 0;
  }
  else {
    state = STATE_NORMAL;
    speed = SPEED_NORMAL;
    brake = 0;
  }

  sendSafetyCommand(state, speed, brake, distanceCm);

  Serial.print("Distance: ");
  Serial.print(distanceCm);
  Serial.print(" cm | State: ");

  if (state == STATE_NORMAL) {
    Serial.print("NORMAL");
  }
  else if (state == STATE_WARNING) {
    Serial.print("WARNING");
  }
  else {
    Serial.print("EMERGENCY");
  }

  Serial.print(" | Speed: ");
  Serial.print(speed);
  Serial.print(" | Brake: ");
  Serial.println(brake);

  delay(100);
}
