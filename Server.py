# backend/server.py
# Producer-Consumer Problem Simulator — Python Backend

import threading
import time
from collections import deque

from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(__name__)
app.config["SECRET_KEY"] = "producer-consumer-secret"
CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


class SimState:
    def __init__(self):
        self.reset()

    def reset(self, buffer_size=6, n_producers=2, n_consumers=2,
              prod_speed=800, cons_speed=1000):

        self.buffer_size = buffer_size
        self.n_producers = n_producers
        self.n_consumers = n_consumers
        self.prod_speed = prod_speed / 1000.0
        self.cons_speed = cons_speed / 1000.0

        self.buffer = [None] * buffer_size
        self.head = 0
        self.tail = 0
        self.count = 0

        self.sem_empty = threading.Semaphore(buffer_size)
        self.sem_full = threading.Semaphore(0)
        self.mutex = threading.Lock()

        self.sem_empty_val = buffer_size
        self.sem_full_val = 0
        self.mutex_val = 1
        self.mutex_holder = "None"

        self.produced = 0
        self.consumed = 0
        self.waiting = 0
        self.item_counter = 1

        self.producer_meta = []
        self.consumer_meta = []

        self.flash_slot = -1
        self.flash_type = ""

        self.running = False
        self.threads = []

        self.log_queue = deque(maxlen=500)
        self.log_lock = threading.Lock()

    def log(self, event_type, thread, msg):
        entry = {"type": event_type, "thread": thread, "msg": msg}
        with self.log_lock:
            self.log_queue.append(entry)

    def snapshot(self):
        return {
            "buffer": list(self.buffer),
            "buffer_size": self.buffer_size,
            "head": self.head,
            "tail": self.tail,
            "count": self.count,
            "sem_empty": self.sem_empty_val,
            "sem_full": self.sem_full_val,
            "mutex": self.mutex_val,
            "mutex_holder": self.mutex_holder,
            "produced": self.produced,
            "consumed": self.consumed,
            "waiting": self.waiting,
            "flash_slot": self.flash_slot,
            "flash_type": self.flash_type,
            "producers": list(self.producer_meta),
            "consumers": list(self.consumer_meta),
        }


sim = SimState()


def producer_thread(thread_id):
    meta = sim.producer_meta[thread_id]
    name = f"P{thread_id + 1}"

    while sim.running:
        speed = sim.prod_speed

        meta["state"] = "running"
        meta["progress"] = 0
        item_val = sim.item_counter
        sim.item_counter += 1

        steps = 20
        for i in range(steps + 1):
            if not sim.running:
                return
            meta["progress"] = (i / steps) * 100
            time.sleep(speed * 0.65 / steps)

        while sim.running:
            if sim.sem_empty.acquire(blocking=False):
                sim.sem_empty_val -= 1
                break
            time.sleep(0.05)

        while sim.running:
            if sim.mutex.acquire(blocking=False):
                sim.mutex_val = 0
                sim.mutex_holder = name
                break
            time.sleep(0.03)

        idx = sim.tail
        sim.buffer[idx] = item_val
        sim.tail = (sim.tail + 1) % sim.buffer_size
        sim.count += 1

        sim.produced += 1
        meta["items"] = meta.get("items", 0) + 1

        sim.mutex_val = 1
        sim.mutex_holder = f"Released by {name}"
        sim.mutex.release()

        sim.sem_full.release()
        sim.sem_full_val += 1

        time.sleep(speed * 0.35)


def consumer_thread(thread_id):
    meta = sim.consumer_meta[thread_id]
    name = f"C{thread_id + 1}"

    while sim.running:
        speed = sim.cons_speed
        meta["state"] = "running"
        meta["progress"] = 0

        while sim.running:
            if sim.sem_full.acquire(blocking=False):
                sim.sem_full_val -= 1
                break
            time.sleep(0.05)

        while sim.running:
            if sim.mutex.acquire(blocking=False):
                sim.mutex_val = 0
                sim.mutex_holder = name
                break
            time.sleep(0.03
