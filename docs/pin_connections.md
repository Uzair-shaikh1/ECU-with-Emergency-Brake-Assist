# Pin Connections

## STM32 to MCP2515 CAN Module

| MCP2515 Pin | STM32 Pin | Description |
|---|---|---|
| VCC | 5V / 3.3V as per module | Power |
| GND | GND | Common ground |
| CS | SPI CS pin | Chip select |
| SCK | SPI SCK | SPI clock |
| MOSI | SPI MOSI | Data from STM32 to MCP2515 |
| MISO | SPI MISO | Data from MCP2515 to STM32 |
| CANH | CANH | CAN high line |
| CANL | CANL | CAN low line |

## Firebird V to MCP2515 CAN Module

| MCP2515 Pin | Firebird V / ATmega2560 Pin | Description |
|---|---|---|
| VCC | 5V | Power |
| GND | GND | Common ground |
| CS | PB0 / SS | SPI chip select |
| SCK | SPI SCK | SPI clock |
| MOSI | SPI MOSI | SPI data |
| MISO | SPI MISO | SPI data |
| CANH | CANH | CAN high line |
| CANL | CANL | CAN low line |
