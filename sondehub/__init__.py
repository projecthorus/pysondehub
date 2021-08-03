import paho.mqtt.client as mqtt
from urllib.parse import urlparse
import http.client
import json
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import sys
import threading
from queue import Queue
import queue
import gzip

S3_BUCKET = "sondehub-history"


class Stream:
    def __init__(self,
                 sondes: list = ["#"],
                 on_connect=None,
                 on_message=None,
                 on_log=None,
                 on_disconnect=None, asJson=False,
                 auto_start_loop=True):
        self.mqttc = mqtt.Client(transport="websockets")
        self._sondes = sondes
        self.asJson = asJson
        self.on_connect = on_connect
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self.on_log = on_log
        self.auto_start_loop = auto_start_loop
        self.ws_connect()

        self.loop_start = self.mqttc.loop_start
        self.loop_stop = self.mqttc.loop_stop
        self.loop = self.mqttc.loop
        self.loop_forever = self.mqttc.loop_forever

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
        try:
            self.mqttc.connect(urlparts.netloc, 443, 60)
        except OSError:
            pass
        if self.auto_start_loop:
            self.mqttc.loop_start()

    def get_url(self):
        conn = http.client.HTTPSConnection("api.v2.sondehub.org")
        conn.request("GET", "/sondes/websocket")
        res = conn.getresponse()
        data = res.read()
        return data.decode("utf-8")

    def _on_message(self, mqttc, obj, msg):
        if self.on_message:
            if self.asJson:
                self.on_message(msg.payload)
            else:
                self.on_message(json.loads(msg.payload))

    def _on_connect(self, mqttc, obj, flags, rc):
        for sonde in self._sondes:
            self.add_sonde(sonde)
        if mqtt.MQTT_ERR_SUCCESS != rc:
            self.ws_connect()
        if self.on_connect:
            self.on_connect(mqttc, obj, flags, rc)

    def _on_log(self, *args, **kwargs):
        if self.on_log:
            self.on_log(*args, **kwargs)

    def _on_disconnect(self, client, userdata, rc):
        try:
            self.ws_connect()
        except OSError:
            pass

        if self.on_disconnect:
            self.on_disconnect(client, userdata, rc)

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
        s3 = boto3.resource("s3", config=Config(signature_version=UNSIGNED))
        while True:
            try:
                task = self.tasks_to_accomplish.get_nowait()
            except queue.Empty:
                return
            if self.debug:
                print(task[1])
            obj = s3.Object(task[0], task[1])
            try:
                with gzip.GzipFile(fileobj=obj.get()["Body"]) as gzipfile:
                    response = json.loads(gzipfile.read())
            except gzip.BadGzipFile:
                response = json.loads(obj.get()["Body"].read())
            if self.debug:
                print(response)
            self.tasks_that_are_done.put(response)
            self.tasks_to_accomplish.task_done()


def download(serial=None, datetime_prefix=None, debug=False):
    if serial:
        prefix_filter = f"serial/{serial}.json.gz"
    elif datetime_prefix:
        prefix_filter = f"date/{datetime_prefix}"
    else:
        prefix_filter = "date/"
    s3 = boto3.resource("s3", config=Config(signature_version=UNSIGNED))
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
        data = data + tasks_that_are_done.get()

    return data
