/*
 * ============================================================
 * Firebird V – CAN Safety Receiver
 * Atmel Studio 7 | AVR-GCC | ATmega2560
 *
 * Result:
 * NORMAL    -> Robot moves forward at maximum speed
 * WARNING   -> Robot moves forward slowly
 * EMERGENCY -> Robot stops
 *
 * LCD:
 * NORMAL FORWARD
 * WARNING SLOW
 * EMERGENCY STOP
 *
 * Motor pins:
 * L1 = PA0
 * L2 = PA1
 * R1 = PA2
 * R2 = PA3
 *
 * PWM:
 * Left  = PL3 / OC5A
 * Right = PL4 / OC5B
 *
 * LCD:
 * RS = PC0
 * RW = PC1
 * EN = PC2
 * D4 = PC4
 * D5 = PC5
 * D6 = PC6
 * D7 = PC7
 *
 * MCP2515:
 * CS   = PB0
 * SCK  = PB1
 * MOSI = PB2
 * MISO = PB3
 * INT  = PE7 / INT7
 *
 * F_CPU = 14.7456 MHz
 * CAN ID = 0x120
 * CAN Speed = 500 kbps
 * ============================================================
 */

#define F_CPU 14745600UL

#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>
#include <stdint.h>

/* ============================================================
   BASIC MACROS
   ============================================================ */

#define sbit(reg, bit)  ((reg) |=  (1 << (bit)))
#define cbit(reg, bit)  ((reg) &= ~(1 << (bit)))

/* ============================================================
   LCD SECTION
   ============================================================ */

#define LCD_PORT    PORTC
#define LCD_DDR     DDRC

#define LCD_RS      0
#define LCD_RW      1
#define LCD_EN      2

static void lcd_pulse_enable(void)
{
    sbit(LCD_PORT, LCD_EN);
    _delay_ms(1);
    cbit(LCD_PORT, LCD_EN);
    _delay_ms(1);
}

static void lcd_send_nibble(uint8_t nibble)
{
    LCD_PORT = (LCD_PORT & 0x0F) | (nibble & 0xF0);
    lcd_pulse_enable();
}

static void lcd_cmd(uint8_t cmd)
{
    cbit(LCD_PORT, LCD_RS);
    cbit(LCD_PORT, LCD_RW);

    lcd_send_nibble(cmd);
    lcd_send_nibble(cmd << 4);

    _delay_ms(2);
}

static void lcd_data(uint8_t data)
{
    sbit(LCD_PORT, LCD_RS);
    cbit(LCD_PORT, LCD_RW);

    lcd_send_nibble(data);
    lcd_send_nibble(data << 4);

    _delay_ms(1);
}

static void lcd_init(void)
{
    LCD_DDR = 0xFF;
    LCD_PORT = 0x00;

    _delay_ms(20);

    LCD_PORT = 0x30;
    lcd_pulse_enable();
    _delay_ms(5);

    LCD_PORT = 0x30;
    lcd_pulse_enable();
    _delay_ms(1);

    LCD_PORT = 0x30;
    lcd_pulse_enable();
    _delay_ms(1);

    LCD_PORT = 0x20;
    lcd_pulse_enable();
    _delay_ms(1);

    lcd_cmd(0x28);   // 4-bit mode, 2 lines
    lcd_cmd(0x0C);   // Display ON, cursor OFF
    lcd_cmd(0x06);   // Auto increment
    lcd_cmd(0x01);   // Clear LCD
    _delay_ms(2);
}

static void lcd_clear(void)
{
    lcd_cmd(0x01);
    _delay_ms(2);
}

static void lcd_cursor(uint8_t row, uint8_t col)
{
    uint8_t address;

    if (row == 1)
        address = 0x80 + col - 1;
    else
        address = 0xC0 + col - 1;

    lcd_cmd(address);
}

static void lcd_string(const char *str)
{
    while (*str)
    {
        lcd_data(*str++);
    }
}

static void lcd_uint16(uint16_t value)
{
    char buffer[6];
    uint8_t i = 0;

    if (value == 0)
    {
        lcd_data('0');
        return;
    }

    while (value > 0)
    {
        buffer[i++] = '0' + (value % 10);
        value = value / 10;
    }

    while (i > 0)
    {
        lcd_data(buffer[--i]);
    }
}

/* ============================================================
   UART2 SECTION
   Firebird V USB serial generally uses UART2
   ============================================================ */

static void uart_init(void)
{
    UBRR2H = 0;
    UBRR2L = 7;   // 115200 baud for 14.7456 MHz

    UCSR2B = (1 << TXEN2);
    UCSR2C = (1 << UCSZ21) | (1 << UCSZ20);
}

static void uart_putc(char c)
{
    while (!(UCSR2A & (1 << UDRE2)));
    UDR2 = c;
}

static void uart_puts(const char *str)
{
    while (*str)
    {
        uart_putc(*str++);
    }
}

static void uart_putu16(uint16_t value)
{
    char buffer[6];
    uint8_t i = 0;

    if (value == 0)
    {
        uart_putc('0');
        return;
    }

    while (value > 0)
    {
        buffer[i++] = '0' + (value % 10);
        value = value / 10;
    }

    while (i > 0)
    {
        uart_putc(buffer[--i]);
    }
}

/* ============================================================
   MOTOR SECTION
   ============================================================ */

static void motor_init(void)
{
    // PA0, PA1, PA2, PA3 as output for direction
    DDRA |= 0x0F;
    PORTA &= 0xF0;

    // PL3 and PL4 as PWM output
    DDRL |= (1 << PL3) | (1 << PL4);

    /*
     * Timer5 Fast PWM 8-bit
     * OC5A = PL3 = Left motor PWM
     * OC5B = PL4 = Right motor PWM
     */
    TCCR5A = (1 << COM5A1) | (1 << COM5B1) | (1 << WGM50);
    TCCR5B = (1 << WGM52) | (1 << CS51);  // Prescaler = 8

    OCR5A = 0;
    OCR5B = 0;
}

static void motor_stop(void)
{
    OCR5A = 0;
    OCR5B = 0;

    PORTA &= 0xF0;
}

static void motor_forward(uint8_t pwm)
{
    /*
     * Corrected forward direction:
     *
     * Left motor:
     * L1 = 1, L2 = 0
     *
     * Right motor:
     * R1 = 0, R2 = 1
     *
     * PA3 PA2 PA1 PA0 = 1 0 0 1 = 0x09
     *
     * This is used because both motors are mounted opposite to each other.
     */
    PORTA = (PORTA & 0xF0) | 0x06;

    OCR5A = pwm;
    OCR5B = pwm;
}

/* ============================================================
   SPI SECTION
   MCP2515 connected by SPI
   ============================================================ */

static void spi_init(void)
{
    // PB0 = CS, PB1 = SCK, PB2 = MOSI output
    DDRB |= (1 << PB0) | (1 << PB1) | (1 << PB2);

    // PB3 = MISO input
    DDRB &= ~(1 << PB3);

    // CS high
    PORTB |= (1 << PB0);

    // SPI enable, master mode
    SPCR = (1 << SPE) | (1 << MSTR);

    // SPI speed fosc/2
    SPSR = (1 << SPI2X);
}

static inline void cs_low(void)
{
    PORTB &= ~(1 << PB0);
}

static inline void cs_high(void)
{
    PORTB |= (1 << PB0);
}

static uint8_t spi_byte(uint8_t data)
{
    SPDR = data;

    while (!(SPSR & (1 << SPIF)));

    return SPDR;
}

/* ============================================================
   MCP2515 SECTION
   ============================================================ */

#define MCP_RESET       0xC0
#define MCP_READ        0x03
#define MCP_WRITE       0x02
#define MCP_BITMOD      0x05
#define MCP_READ_RX0    0x90

#define MCP_CANSTAT     0x0E
#define MCP_CANCTRL     0x0F
#define MCP_CNF3        0x28
#define MCP_CNF2        0x29
#define MCP_CNF1        0x2A
#define MCP_CANINTE     0x2B
#define MCP_CANINTF     0x2C
#define MCP_RXB0CTRL    0x60

#define MCP_RXM0SIDH    0x20
#define MCP_RXM0SIDL    0x21
#define MCP_RXF0SIDH    0x00
#define MCP_RXF0SIDL    0x01

#define MODE_CONFIG     0x80
#define MODE_NORMAL     0x00

#define RXIF0           0x01

static void mcp_write_reg(uint8_t address, uint8_t value)
{
    cs_low();

    spi_byte(MCP_WRITE);
    spi_byte(address);
    spi_byte(value);

    cs_high();
}

static uint8_t mcp_read_reg(uint8_t address)
{
    uint8_t value;

    cs_low();

    spi_byte(MCP_READ);
    spi_byte(address);
    value = spi_byte(0xFF);

    cs_high();

    return value;
}

static void mcp_bitmod(uint8_t address, uint8_t mask, uint8_t value)
{
    cs_low();

    spi_byte(MCP_BITMOD);
    spi_byte(address);
    spi_byte(mask);
    spi_byte(value);

    cs_high();
}

static void mcp_reset(void)
{
    cs_low();
    spi_byte(MCP_RESET);
    cs_high();

    _delay_ms(10);
}

static uint8_t mcp_init(void)
{
    mcp_reset();

    // Configuration mode
    mcp_write_reg(MCP_CANCTRL, MODE_CONFIG);
    _delay_ms(5);

    if ((mcp_read_reg(MCP_CANSTAT) & 0xE0) != MODE_CONFIG)
    {
        return 0;
    }

    /*
     * CAN speed = 500 kbps
     * MCP2515 crystal = 8 MHz
     */
    mcp_write_reg(MCP_CNF1, 0x00);
    mcp_write_reg(MCP_CNF2, 0x90);
    mcp_write_reg(MCP_CNF3, 0x02);

    // RXB0 filter enabled
    mcp_write_reg(MCP_RXB0CTRL, 0x00);

    // Mask for standard 11-bit ID
    mcp_write_reg(MCP_RXM0SIDH, 0xFF);
    mcp_write_reg(MCP_RXM0SIDL, 0xE0);

    /*
     * Accept only CAN ID 0x120
     * SIDH = 0x120 >> 3 = 0x24
     * SIDL = 0x00
     */
    mcp_write_reg(MCP_RXF0SIDH, 0x24);
    mcp_write_reg(MCP_RXF0SIDL, 0x00);

    // Enable RX0 interrupt
    mcp_write_reg(MCP_CANINTE, RXIF0);

    // Normal mode
    mcp_write_reg(MCP_CANCTRL, MODE_NORMAL);
    _delay_ms(5);

    if ((mcp_read_reg(MCP_CANSTAT) & 0xE0) != MODE_NORMAL)
    {
        return 0;
    }

    return 1;
}

/* ============================================================
   CAN FRAME READ SECTION
   ============================================================ */

typedef struct
{
    uint16_t id;
    uint8_t dlc;
    uint8_t data[8];
} can_frame_t;

static void mcp_read_rx0(can_frame_t *frame)
{
    uint8_t sidh;
    uint8_t sidl;
    uint8_t dlc;

    cs_low();

    spi_byte(MCP_READ_RX0);

    sidh = spi_byte(0xFF);
    sidl = spi_byte(0xFF);

    spi_byte(0xFF);  // EID8 not used
    spi_byte(0xFF);  // EID0 not used

    dlc = spi_byte(0xFF) & 0x0F;

    frame->id = ((uint16_t)sidh << 3) | (sidl >> 5);
    frame->dlc = dlc;

    for (uint8_t i = 0; i < dlc && i < 8; i++)
    {
        frame->data[i] = spi_byte(0xFF);
    }

    cs_high();

    // Clear RX0 interrupt flag
    mcp_bitmod(MCP_CANINTF, RXIF0, 0x00);
}

/* ============================================================
   INT7 SECTION
   MCP2515 INT connected to PE7 / INT7
   ============================================================ */

volatile uint8_t can_flag = 0;

ISR(INT7_vect)
{
    can_flag = 1;
}

static void int7_init(void)
{
    // PE7 input
    cbit(DDRE, PE7);

    // Pull-up enable
    sbit(PORTE, PE7);

    // INT7 falling edge
    EICRB = (EICRB & ~(0x03 << 6)) | (0x02 << 6);

    // Enable INT7
    sbit(EIMSK, INT7);
}

/* ============================================================
   TIMER1 MILLIS SECTION
   ============================================================ */

volatile uint32_t ms_ticks = 0;

ISR(TIMER1_OVF_vect)
{
    TCNT1 = 0xFF1A;
    ms_ticks++;
}

static void timer1_init(void)
{
    TCCR1A = 0;

    // Prescaler = 64
    TCCR1B = (1 << CS11) | (1 << CS10);

    TCNT1 = 0xFF1A;

    // Timer1 overflow interrupt enable
    TIMSK1 = (1 << TOIE1);
}

static uint32_t millis(void)
{
    uint32_t time_now;
    uint8_t old_sreg = SREG;

    cli();
    time_now = ms_ticks;
    SREG = old_sreg;

    return time_now;
}

/* ============================================================
   APPLICATION SECTION
   ============================================================ */

#define STATE_NORMAL      0
#define STATE_WARNING     1
#define STATE_EMERGENCY   2

#define PWM_NORMAL        255     // Maximum speed
#define PWM_WARNING       190     // Slow speed
#define CAN_TIMEOUT_MS    500UL

static uint8_t g_state = STATE_EMERGENCY;
static uint8_t g_last_ctr = 255;
static uint32_t g_last_frame_ms = 0;

static uint8_t calc_checksum(uint8_t b0, uint8_t b1, uint8_t b2,
                             uint8_t b3, uint8_t b4, uint8_t b5)
{
    return b0 ^ b1 ^ b2 ^ b3 ^ b4 ^ b5;
}

static void update_lcd(uint8_t state, uint16_t distance)
{
    lcd_clear();

    lcd_cursor(1, 1);

    if (state == STATE_NORMAL)
    {
        lcd_string("NORMAL FORWARD ");
    }
    else if (state == STATE_WARNING)
    {
        lcd_string("WARNING SLOW   ");
    }
    else if (state == STATE_EMERGENCY)
    {
        lcd_string("EMERGENCY STOP ");
    }
    else
    {
        lcd_string("UNKNOWN STATE  ");
    }

    lcd_cursor(2, 1);
    lcd_string("Dist:");

    if (distance == 999)
    {
        lcd_string("ERR      ");
    }
    else
    {
        lcd_uint16(distance);
        lcd_string("cm       ");
    }
}

static void apply_state(uint8_t state, uint16_t distance)
{
    if (state == STATE_NORMAL)
    {
        motor_forward(PWM_NORMAL);
    }
    else if (state == STATE_WARNING)
    {
        motor_forward(PWM_WARNING);
    }
    else if (state == STATE_EMERGENCY)
    {
        motor_stop();
    }
    else
    {
        motor_stop();
    }

    update_lcd(state, distance);
}

/* ============================================================
   MAIN FUNCTION
   ============================================================ */

int main(void)
{
    can_frame_t frame;

    uint8_t rx_state;
    uint8_t rx_speed;
    uint8_t rx_brake;
    uint8_t d_low;
    uint8_t d_high;
    uint8_t rx_ctr;
    uint8_t rx_chk;

    uint16_t distance;

    // Initialize peripherals
    spi_init();
    uart_init();
    motor_init();
    timer1_init();
    int7_init();

    sei();

    // LCD startup
    lcd_init();
    lcd_cursor(1, 1);
    lcd_string("Firebird CAN RX");

    lcd_cursor(2, 1);
    lcd_string("Starting...    ");

    _delay_ms(1500);

    uart_puts("\r\n====================================\r\n");
    uart_puts("Firebird V CAN Safety Receiver\r\n");
    uart_puts("Motor direction corrected\r\n");
    uart_puts("NORMAL = Forward Maximum Speed\r\n");
    uart_puts("====================================\r\n");

    // MCP2515 initialization
    if (!mcp_init())
    {
        uart_puts("ERROR: MCP2515 INIT FAILED\r\n");

        lcd_clear();
        lcd_cursor(1, 1);
        lcd_string("CAN INIT ERROR ");

        lcd_cursor(2, 1);
        lcd_string("Check MCP2515  ");

        motor_stop();

        while (1)
        {
            // Stop here if CAN init fails
        }
    }

    uart_puts("MCP2515 OK. Waiting for STM32 CAN frames...\r\n");

    lcd_clear();
    lcd_cursor(1, 1);
    lcd_string("CAN OK         ");

    lcd_cursor(2, 1);
    lcd_string("Waiting STM32  ");

    g_last_frame_ms = millis();

    while (1)
    {
        if (can_flag)
        {
            can_flag = 0;

            if (mcp_read_reg(MCP_CANINTF) & RXIF0)
            {
                mcp_read_rx0(&frame);

                if (frame.id == 0x120 && frame.dlc == 7)
                {
                    rx_state = frame.data[0];
                    rx_speed = frame.data[1];
                    rx_brake = frame.data[2];
                    d_low    = frame.data[3];
                    d_high   = frame.data[4];
                    rx_ctr   = frame.data[5];
                    rx_chk   = frame.data[6];

                    // Check checksum
                    if (calc_checksum(rx_state, rx_speed, rx_brake,
                                      d_low, d_high, rx_ctr) != rx_chk)
                    {
                        uart_puts("Bad checksum received\r\n");
                        continue;
                    }

                    // Counter check
                    if (g_last_ctr != 255)
                    {
                        if (rx_ctr != (uint8_t)(g_last_ctr + 1))
                        {
                            uart_puts("Warning: missed CAN frame\r\n");
                        }
                    }

                    g_last_ctr = rx_ctr;
                    g_last_frame_ms = millis();

                    distance = ((uint16_t)d_high << 8) | d_low;

                    g_state = rx_state;

                    apply_state(g_state, distance);

                    uart_puts("[CAN] ");

                    if (g_state == STATE_NORMAL)
                    {
                        uart_puts("NORMAL ");
                    }
                    else if (g_state == STATE_WARNING)
                    {
                        uart_puts("WARNING ");
                    }
                    else if (g_state == STATE_EMERGENCY)
                    {
                        uart_puts("EMERGENCY ");
                    }
                    else
                    {
                        uart_puts("UNKNOWN ");
                    }

                    uart_puts("| Distance = ");
                    uart_putu16(distance);
                    uart_puts(" cm");

                    uart_puts(" | Counter = ");
                    uart_putu16(rx_ctr);

                    uart_puts("\r\n");
                }
            }
        }

        // CAN timeout protection
        if ((millis() - g_last_frame_ms) > CAN_TIMEOUT_MS)
        {
            if (g_state != STATE_EMERGENCY)
            {
                uart_puts("CAN timeout. Robot stopped.\r\n");

                g_state = STATE_EMERGENCY;
                apply_state(STATE_EMERGENCY, 999);
            }
        }
    }

    return 0;
}
