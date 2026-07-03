# System Architecture

The Safety Supervisor ECU receives sensor data from LIDAR and IMU sensors.

The STM32 works as the main ECU. It processes obstacle distance and vehicle condition, then sends safety commands over CAN bus.

The Firebird V robot receives CAN messages through the MCP2515 CAN module and changes motor action according to the received state.

## Working States

| State | Condition | Robot Response |
|---|---|---|
| Normal | Safe distance | Robot moves normally |
| Warning | Obstacle detected in warning range | Robot slows down |
| Emergency | Obstacle very close | Robot stops |

## Communication Flow

LIDAR + IMU  
↓  
STM32 ECU  
↓  
MCP2515 CAN Transmitter  
↓  
CAN Bus  
↓  
MCP2515 CAN Receiver  
↓  
Firebird V Robot  
↓  
Motor response + LCD display
