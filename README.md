# SondeHub (and SondeHub-Amateur) Python Library

This repository contains:
* A uploader class for submitting high-altitude balloon telemetry data to SondeHub-Amateur
* A simple realtime streaming SDK for the sondehub.org V2 API (both radiosondes, and amateur balloons).

### Contacts
* [Mark Jessop](https://github.com/darksidelemm) - vk5qi@rfhead.net
* [Michaela Wheeler](https://github.com/TheSkorm) - radiosonde@michaela.lgbt

You can often find us in the #highaltitude IRC Channel on Libera Chat.

## Installing
This library is available via pypi, and can be installed into your Python environment using:
```
pip install sondehub
```

## Submitting Telemetry to SondeHub-Amateur
A guide on using the SondeHub-Amateur uploader class is available here https://github.com/projecthorus/pysondehub/wiki/SondeHub-Amateur-Uploader-Class-Usage

## Streaming Telemetry Data

```
sondehub.Stream(sondes=["serial number"], on_message=callback)
```
If no `sondes` list is provided then all radiosondes will be streamed.

On message callback will contain a python dictonary using the [Universal Sonde Telemetry Format](https://github.com/projecthorus/radiosonde_auto_rx/wiki/SondeHub-DB-Universal-Telemetry-Format)


```
sondehub.Stream().add_sonde(serial)
sondehub.Stream().remove_sonde(serial)
```

Adds or removes a radiosonde from the filter

### Data license

Data is provided under the [Creative Commons BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/) license.

### Example Usage


```python
import sondehub

def on_message(message):
    print(message)

test = sondehub.Stream(sondes=["R3320848"], on_message=on_message)
#test = sondehub.Stream(on_message=on_message)
while 1:
    pass

```

### Advanced Usage

Manual usage of the Paho MQTT network loop can be obtained by using the `loop`, `loop_forever`, `loop_start` and `loop_stop` functions, taking care to ensure that the different types of network loop aren't mixed. See Paho documentation [here](https://www.eclipse.org/paho/index.php?page=clients/python/docs/index.php#network-loop).

```python
test = sondehub.Stream(on_message=on_message, sondes=sondes, auto_start_loop=False)
test.loop_forever()
```

### CLI Usage
#### Live streaming data
```sh
# all radiosondes
sondehub
# single radiosonde
sondehub --serial "IMET-73217972"
# multiple radiosondes
sondehub --serial "IMET-73217972" --serial "IMET-73217973"
#pipe in jq
sondehub | jq .
{
  "subtype": "SondehubV1",
  "temp": "-4.0",
  "manufacturer": "SondehubV1",
  "serial": "IMET54-55067143",
  "lat": "-25.95437",
  "frame": "85436",
  "datetime": "2021-02-01T23:43:57.043655Z",
  "software_name": "SondehubV1",
  "humidity": "97.8",
  "alt": "5839",
  "vel_h": "-9999.0",
  "uploader_callsign": "ZS6TVB",
  "lon": "28.19082",
  "software_version": "SondehubV1",
  "type": "SondehubV1",
  "time_received": "2021-02-01T23:43:57.043655Z",
  "position": "-25.95437,28.19082"
}
....

```

#### Downloading data
```
sondehub --download S2810113
```


## Open Data Access

A basic interface to the Open Data is a available using `sondehub.download(serial=, datetime_prefix=)`. When using datetime_prefix only summary data is provided (the oldest, newest and highest frames)

```
import sondehub
frames = sondehub.download(datetime_prefix="2018/10/01")
frames = sondehub.download(serial="serial")
```