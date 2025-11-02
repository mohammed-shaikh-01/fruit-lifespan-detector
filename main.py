import machine
import utime
import dht
import math

# --- LCD Class (unchanged from your version) ---
class LCD:
    def __init__(self, rs, e, d4, d5, d6, d7):
        self.rs = machine.Pin(rs, machine.Pin.OUT)
        self.e = machine.Pin(e, machine.Pin.OUT)
        self.d4 = machine.Pin(d4, machine.Pin.OUT)
        self.d5 = machine.Pin(d5, machine.Pin.OUT)
        self.d6 = machine.Pin(d6, machine.Pin.OUT)
        self.d7 = machine.Pin(d7, machine.Pin.OUT)

        # Init sequence
        self.send_command(0x33)
        self.send_command(0x32)
        self.send_command(0x28)
        self.send_command(0x0C)
        self.send_command(0x06)
        self.send_command(0x01)
        utime.sleep_ms(2)

    def send_command(self, cmd):
        self.set_data_pins(cmd >> 4)
        self.rs.value(0)
        self.e.value(1); utime.sleep_us(5)
        self.e.value(0); utime.sleep_us(100)

        self.set_data_pins(cmd & 0x0F)
        self.rs.value(0)
        self.e.value(1); utime.sleep_us(5)
        self.e.value(0); utime.sleep_us(100)

    def send_data(self, data):
        self.set_data_pins(data >> 4)
        self.rs.value(1)
        self.e.value(1); utime.sleep_us(5)
        self.e.value(0); utime.sleep_us(100)

        self.set_data_pins(data & 0x0F)
        self.rs.value(1)
        self.e.value(1); utime.sleep_us(5)
        self.e.value(0); utime.sleep_us(100)

    def set_data_pins(self, value):
        self.d4.value((value >> 0) & 1)
        self.d5.value((value >> 1) & 1)
        self.d6.value((value >> 2) & 1)
        self.d7.value((value >> 3) & 1)

    def clear(self):
        self.send_command(0x01)
        utime.sleep_ms(2)

    def set_cursor(self, col, row):
        if row == 0:
            self.send_command(0x80 | col)
        else:
            self.send_command(0xC0 | col)

    def putstr(self, text):
        for char in text:
            self.send_data(ord(char))

# --- Hardware Config ---
dht_pin = machine.Pin(16)
mq4_pin = machine.ADC(26)
buzzer = machine.Pin(17, machine.Pin.OUT)
red_light = machine.Pin(14, machine.Pin.OUT)
green_light = machine.Pin(15, machine.Pin.OUT)

# UART1 on GP8 (TX) & GP9 (RX)
uart = machine.UART(0, baudrate=115200, tx=machine.Pin(0), rx=machine.Pin(1))

# WiFi & ThingSpeak
WIFI_SSID = "Usmani's"
WIFI_PASSWORD = "z4zahera"
THINGSPEAK_API_KEY = "O9Z1P54QOGL0W7JW"
THINGSPEAK_URL = "http://api.thingspeak.com/update"

# Init sensors & LCD
dht_sensor = dht.DHT11(dht_pin)
lcd = LCD(rs=2, e=3, d4=4, d5=5, d6=6, d7=7)

def calculate_lifespan(humidity, temp, methane_emission, lifespan_constant=2000.0):
    if methane_emission <= 0:
        methane_emission = 1
    lifespan = (humidity / 100.0) * math.exp(0.05 * (temp - 20.0)) * (lifespan_constant / methane_emission)
    return 4 - lifespan

def display_message(line1, line2=""):
    utime.sleep_ms(100)
    lcd.clear()
    utime.sleep_ms(100)
    lcd.putstr(line1)
    if line2:
        lcd.set_cursor(0, 1)
        lcd.putstr(line2)

def connect_wifi(ssid, password):
    uart.write("AT+RST\r\n")
    utime.sleep(2)
    uart.read()

    display_message("Connecting...", ssid)
    uart.write('AT+CWMODE=1\r\n')
    utime.sleep(1)
    uart.write(f'AT+CWJAP="{ssid}","{password}"\r\n')

    timeout = 20
    start = utime.time()
    while utime.time() - start < timeout:
        if uart.any():
            resp = uart.read().decode("utf-8", "ignore")
            print("ESP8266:", resp)
            if "WIFI GOT IP" in resp or "OK" in resp:
                display_message("Wi-Fi", "Connected")
                return True
        utime.sleep(1)
    display_message("Wi-Fi Failed")
    return False

def send_to_thingspeak(temp, hum, methane, life):
    display_message("Sending Data", "ThingSpeak")

    url = f"{THINGSPEAK_URL}?api_key={THINGSPEAK_API_KEY}&field1={temp}&field2={hum}&field3={methane}&field4={life}"
    host = "api.thingspeak.com"
    request_data = f"GET /update?api_key={THINGSPEAK_API_KEY}&field1={temp}&field2={hum}&field3={methane}&field4={life} HTTP/1.1\r\nHost: {host}\r\n\r\n"

    uart.write("AT+CIPCLOSE\r\n")
    utime.sleep(1)
    uart.write(f'AT+CIPSTART="TCP","{host}",80\r\n')
    utime.sleep(2)
    uart.write(f'AT+CIPSEND={len(request_data)}\r\n')
    utime.sleep(1)
    uart.write(request_data)
    utime.sleep(2)

    if uart.any():
        resp = uart.read().decode("utf-8", "ignore")
        print("ThingSpeak Resp:", resp)
        if "200 OK" in resp:
            display_message("Data Sent!", "Success")

def buzzer_switch(lifespan):
    if lifespan < 3:
        buzzer.value(1)
        utime.sleep(.5)
        buzzer.value(0)
        utime.sleep(.2)
    
def light_switch(lifespan):
    if lifespan < 1:
        green_light.value(0)
        utime.sleep(.2)
        red_light.value(1)
    elif lifespan > 2:
        red_light.value(0)
        utime.sleep(.2)
        green_light.value(1)
    else:
        red_light.value(0)
        green_light.value(0)


# --- Main Loop ---
if connect_wifi(WIFI_SSID, WIFI_PASSWORD):
    while True:
        try:
            dht_sensor.measure()

            temp = dht_sensor.temperature()
            hum = dht_sensor.humidity()
            raw_val = mq4_pin.read_u16()
            methane_ppm = int((raw_val / 65535) * 1000)

            life = calculate_lifespan(humidity=hum, temp=temp, methane_emission=methane_ppm)
            buzzer_switch(life)
            light_switch(life)
            print(f"Temp={temp}C  Hum={hum}%  Gas={methane_ppm}ppm Life={life}days")
            send_to_thingspeak(temp, hum, raw_val, life)
            display_message(f"T:{temp}C H:{hum}%", f"ML:{methane_ppm}ppm L:{life}days",)

        except Exception as e:
            print("Error:", e)
            display_message("Sensor Error")

        utime.sleep(60)  # >=15s due to ThingSpeak limit
