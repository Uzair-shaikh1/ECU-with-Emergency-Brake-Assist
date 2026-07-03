# STM32 ECU Code

This folder contains the STM32 Safety Supervisor ECU code.

The STM32 reads sensor data from LIDAR and IMU sensors, processes the safety condition, and sends the safety command over CAN communication.

## Main Function

- Reads distance and motion data
- Determines Normal, Warning, or Emergency state
- Sends safety command through MCP2515 CAN module
