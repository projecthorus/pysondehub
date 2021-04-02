import json
import time
import sondehub

interval = 5
msgs = 0
elapsed = 0
starttime = 0
log = True

def on_msg(*args):
    global msgs
    msgs +=1

def on_connect(*args):
    print("on_connect:", *args)

def on_disconnect(*args):
    print("on_disconnect:", *args)

def on_log(*args):
    if log:
        print(f"on_log:", *args)

sh  = sondehub.Stream(on_message=on_msg,
                      on_disconnect=on_disconnect,
                      on_log=on_log,
                      on_connect=on_connect);
while True:
    time.sleep(interval)
    print(f"tick {msgs=}")
    msgs = 0
