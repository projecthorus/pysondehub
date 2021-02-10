import paho.mqtt.client as mqtt
from urllib.parse import urlparse
import http.client
import json
import boto3
import sys
import threading
from queue import Queue
import queue


S3_BUCKET = "sondehub-open-data"


class Stream:
    def __init__(self, sondes: list = ["#"], on_connect=None, on_message=None):
        self.mqttc = mqtt.Client(transport="websockets")
        self._sondes = sondes
        self.ws_connect()
        self.on_connect = on_connect
        self.on_message = on_message

    def add_sonde(self, sonde):
        if sonde not in self._sondes:
            self._sondes.append(sonde)
        (result, mid) = self.mqttc.subscribe(f"sondes/{sonde}", 0)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self.ws_connect()

    def remove_sonde(self, sonde):
        self._sondes.remove(sonde)
        (result, mid) = self.mqttc.unsubscribe(f"sondes/{sonde}", 0)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self.ws_connect()

    def ws_connect(self):
        url = self.get_url()
        urlparts = urlparse(url)
        headers = {
            "Host": "{0:s}".format(urlparts.netloc),
        }

        self.mqttc.on_message = self._on_message  # self.on_message
        self.mqttc.on_connect = self._on_connect
        self.mqttc.on_disconnect = self._on_disconnect

        self.mqttc.ws_set_options(
            path="{}?{}".format(urlparts.path, urlparts.query), headers=headers
        )
        try:
            self.mqttc.tls_set()
        except ValueError:
            pass
        self.mqttc.connect(urlparts.netloc, 443, 60)
        self.mqttc.loop_start()
        for sonde in self._sondes:
            self.add_sonde(sonde)

    def get_url(self):
        conn = http.client.HTTPSConnection("api.v2.sondehub.org")
        conn.request("GET", "/sondes/websocket")
        res = conn.getresponse()
        data = res.read()
        return data.decode("utf-8")

    def _on_message(self, mqttc, obj, msg):
        if self.on_message:
            self.on_message(json.loads(msg.payload))

    def _on_connect(self, mqttc, obj, flags, rc):
        if mqtt.MQTT_ERR_SUCCESS != rc:
            self.ws_connect()
        if self.on_connect:
            self.on_connect()

    def _on_disconnect(self, client, userdata, rc):
        self.ws_connect()

    def __exit__(self, type, value, traceback):
        self.mqttc.disconnect()

    def disconnect(self):
        self.mqttc.disconnect()


class Downloader(threading.Thread):
    def __init__(
        self, tasks_to_accomplish, tasks_that_are_done, debug=False, *args, **kwargs
    ):
        self.tasks_to_accomplish = tasks_to_accomplish
        self.tasks_that_are_done = tasks_that_are_done
        self.debug = debug
        super().__init__(*args, **kwargs)

    def run(self):
        s3 = boto3.client("s3")
        while True:
            try:
                task = self.tasks_to_accomplish.get_nowait()
            except queue.Empty:
                return
            data = s3.get_object(Bucket=task[0], Key=task[1])
            response = json.loads(data["Body"].read())
            if self.debug:
                print(response)
            self.tasks_that_are_done.put(response)
            self.tasks_to_accomplish.task_done()


def download(serial=None, datetime_prefix=None, debug=False):
    if serial:
        prefix_filter = f"serial/{serial}/"
    elif serial and datetime_prefix:
        prefix_filter = f"serial/{serial}/{datetime_prefix}"
    elif datetime_prefix:
        prefix_filter = f"date/{datetime_prefix}"
    else:
        prefix_filter = "date/"

    s3 = boto3.resource("s3")
    bucket = s3.Bucket(S3_BUCKET)
    data = []

    number_of_processes = 50
    tasks_to_accomplish = Queue()
    tasks_that_are_done = Queue()

    for s3_object in bucket.objects.filter(Prefix=prefix_filter):
        tasks_to_accomplish.put((s3_object.bucket_name, s3_object.key))

    for _ in range(number_of_processes):
        Downloader(tasks_to_accomplish, tasks_that_are_done, debug).start()
    tasks_to_accomplish.join()

    while not tasks_that_are_done.empty():
        data.append(tasks_that_are_done.get())

    return data
