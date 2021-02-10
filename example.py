import sondehub
from multiprocessing import Queue
# def on_message(message):
#     print(f"{message['serial']} - {message['alt']}")

# test = sondehub.Stream(on_message=on_message)
# while 1:
#     pass

print(sondehub.download(serial="S1120364"))
#print(sondehub.download(datetime_prefix="2021-02-04T02:19"))
# tasks_to_accomplish = Queue()
# blah = Queue()
# tasks_to_accomplish.put(("sondehub-open-data","serial/S1120364/2020-10-18T01:10:12.152254Z-5fb87ccb-7a0e-4975-b39f-593e19bc2bcd.json"))

# print(sondehub.parallel_download(tasks_to_accomplish,blah))