import RPi.GPIO as GPIO
import threading
import datetime
import requests
import time
from concurrent.futures import ThreadPoolExecutor


class Runner:
    def __init__(self):
        # scores
        self.p1 = 0
        self.p2 = 0

        # buttons and lights
        self.b1 = 17
        self.b2 = 20
        self.b1_light = 27
        self.b2_light = 21
        self.s1_trigger = 18
        self.s1_echo = 24

        self.timeout_off = 5

        # bounce time for buttons
        self.bouncetime = 5

        # active state
        self.last_used = datetime.datetime.now()
        self.on = True

        # distance threshold
        self.distance_threshold = 100

        # lights configuration
        self.ip_address = 'http://192.168.43.64'
        # self.ip_address = 'http://localhost'
        self.color_sleep = 0.5

        self.executor = ThreadPoolExecutor(5)

    def push_button(self, channel):
        if GPIO.input(channel) == 1:
            GPIO.output(self.b1_light, 1)
            GPIO.output(self.b2_light, 1)
            if channel == self.b1:
                self.score(1)
                print('finished scoring')
            elif channel == self.b2:
                self.score(2)
            reset_thread = threading.Thread(target=self.reset_timer, args=(channel,))
            reset_thread.start()
        else:
            GPIO.output(self.b1_light, 0)
            GPIO.output(self.b2_light, 0)

    def reset_timer(self, channel):
        time.sleep(2.5)
        if GPIO.input(channel) == 1:
            self.turn_on()
            self.reset()

    def distance(self):
        # set Trigger to HIGH
        GPIO.output(self.s1_trigger, True)

        # set Trigger after 0.01ms to LOW
        time.sleep(0.00001)
        GPIO.output(self.s1_trigger, False)

        StartTime = time.time()
        StopTime = time.time()

        # save StartTime
        while GPIO.input(self.s1_echo) == 0:
            StartTime = time.time()

        # save time of arrival
        while GPIO.input(self.s1_echo) == 1:
            StopTime = time.time()

        # time difference between start and arrival
        TimeElapsed = StopTime - StartTime
        # multiply with the sonic speed (34300 cm/s)
        # and divide by 2, because there and back
        distance = (TimeElapsed * 34300) / 2

        return distance

    def distance_activator(self):
        dist = self.distance()
        # print((datetime.datetime.now() - self.last_used).total_seconds())
        print("Measured Distance = %.1f cm" % dist)
        if dist < self.distance_threshold:
            self.turn_on()

    def run_gpio(self):
        GPIO.setmode(GPIO.BCM)

        # sonar 1 gpio setup
        GPIO.setup(self.s1_trigger, GPIO.OUT)
        GPIO.setup(self.s1_echo, GPIO.IN)

        # button gpio setup
        GPIO.setup(self.b1_light, GPIO.OUT)
        GPIO.setup(self.b2_light, GPIO.OUT)

        GPIO.setup(self.b1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.b2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        cb_1 = ButtonHandler(self.b1, self.push_button, edge='both', bouncetime=self.bouncetime)
        cb_2 = ButtonHandler(self.b2, self.push_button, edge='both', bouncetime=self.bouncetime)
        cb_1.start()
        cb_2.start()
        GPIO.add_event_detect(self.b1, GPIO.RISING, callback=cb_1)
        GPIO.add_event_detect(self.b2, GPIO.RISING, callback=cb_2)

        while True:
            self.executor.submit(self.distance_activator)
            if (datetime.datetime.now() - self.last_used).total_seconds() > self.timeout_off:
                self.turn_off()

    def score(self, player):
        self.turn_on()
        if player == 1:
            self.p1 += 1
        if player == 2:
            self.p2 += 1
        self.executor.submit(self.send_request, 'http://localhost:5000/api/set', 'get', {'playerOne': self.p1, 'playerTwo': self.p2})
        self.executor.submit(self.flash_colors)

    def flash_colors(self):
        print('start col')
        self.set_color('#FFFFFFFF')
        # time.sleep(3)
        time.sleep(self.color_sleep)
        time.sleep(self.color_sleep)
        self.set_color('#FFFFFFFF')
        print('end col')

    def reset(self):
        self.p1 = 0
        self.p2 = 0
        self.executor.submit(self.send_request, 'http://localhost:5000/api/reset', 'get')

    def turn_off(self):
        self.executor.submit(self.send_request, 'http://localhost:5000/api/off', 'get')
        self.on = False
        self.reset()

    def turn_on(self):
        if not self.on:
            self.on = True
            self.executor.submit(self.send_request, 'http://localhost:5000/api/on', 'get')
        self.last_used = datetime.datetime.now()

    def set_color(self, colorNum):
        requests.get(self.ip_address + '/cm?cmnd=Color%20' + str(colorNum))

    def set_white(self, whiteNum):
        requests.get(self.ip_address + '/cm?cmnd=White%20' + str(whiteNum))

    def set_brightness(self, brightness):
        requests.get(self.ip_address + '/cm?cmnd=Dimmer%20' + str(brightness))

    def run_lights(self):
        for x in range(1, 10):
            set_color(x);

    def send_request(self, url, request_type, content=None):
        if request_type == 'get':
            r = requests.get(url)
        if request_type == 'post':
            r = request.post(url, content)


class ButtonHandler(threading.Thread):
    def __init__(self, pin, func, edge='both', bouncetime=200):
        super().__init__(daemon=True)

        self.edge = edge
        self.func = func
        self.pin = pin
        self.bouncetime = float(bouncetime)/1000

        self.lastpinval = GPIO.input(self.pin)
        self.lock = threading.Lock()

    def __call__(self, *args):
        if not self.lock.acquire(blocking=False):
            return

        t = threading.Timer(self.bouncetime, self.read, args=args)
        t.start()

    def read(self, *args):
        pinval = GPIO.input(self.pin)

        if (
                ((pinval == 0 and self.lastpinval == 1) and
                 (self.edge in ['falling', 'both'])) or
                ((pinval == 1 and self.lastpinval == 0) and
                 (self.edge in ['rising', 'both']))
        ):
            self.func(*args)

        self.lastpinval = pinval
        self.lock.release()

if __name__ == '__main__':
    runner = Runner()
    try:
        runner.run_gpio()
    except Exception as e:
        print(e)
        GPIO.cleanup()
