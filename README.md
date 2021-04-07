Simple realtime streaming SDK for sondehub.org V2 API.

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

Data license
--
Data is provided under the [Creative Commons BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/) license.

Example Usage
--

```python
import sondehub

def on_message(message):
    print(message)

test = sondehub.Stream(sondes=["R3320848"], on_message=on_message)
#test = sondehub.Stream(on_message=on_message)
while 1:
    pass

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
sondehub --download S2810113 # Note this may take a long time to finish!
```


Open Data Access
==

A basic interface to the Open Data is a available using `sondehub.download(serial=None, datetime_prefix=None)`

```
import sondehub
frames = sondehub.download(datetime_prefix="2018-10-01")
frames = sondehub.download(serial="serial")
```