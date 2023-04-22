#!/usr/bin/env python
#
#   SondeHub Amateur Uploader
#
#   Uploads telemetry to the SondeHub ElasticSearch cluster,
#   in the new 'universal' format descried here:
#   https://github.com/projecthorus/sondehub-infra/wiki/%5BDRAFT%5D-Amateur-Balloon-Telemetry-Format
#
#   Copyright (C) 2022  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import sondehub
import datetime
import glob
import gzip
import json
import logging
import os
import requests
import time
from threading import Thread
from email.utils import formatdate
from queue import Queue
from dateutil.parser import parse
    

def fix_datetime(datetime_str, local_dt_str=None):
    """
	Given a HH:MM:SS string from a telemetry sentence, produce a complete timestamp, 
    using the current system time as a guide for the date.
	"""

    if local_dt_str is None:
        _now = datetime.datetime.utcnow()
    else:
        _now = parse(local_dt_str)

    # Are we in the rollover window?
    if _now.hour == 23 or _now.hour == 0:
        _outside_window = False
    else:
        _outside_window = True

    # Parsing just a HH:MM:SS will return a datetime object with the year, month and day replaced by values in the 'default'
    # argument.
    # If the year/month/date has also been provided, then we just end up with the supplied time.
    _new_dt = parse(datetime_str, default=_now)

    if _outside_window:
        # We are outside the day-rollover window, and can safely use the current zulu date.
        return _new_dt
    else:
        # We are within the window, and need to adjust the day backwards or forwards based on the sonde time.
        if _new_dt.hour == 23 and _now.hour == 0:
            # Assume system clock running slightly fast, and subtract a day from the telemetry date.
            _new_dt = _new_dt - datetime.timedelta(days=1)

        elif _new_dt.hour == 00 and _now.hour == 23:
            # System clock running slow. Add a day.
            _new_dt = _new_dt + datetime.timedelta(days=1)

        return _new_dt


class Uploader(object):
    """ Sondehub (Amateur) Uploader Class.

    Accepts telemetry data in various forms, buffers them up, and then compresses and uploads
    them to the Sondehub Elasticsearch cluster.

    """

    # SondeHub API endpoint
    SONDEHUB_AMATEUR_URL = "https://api.v2.sondehub.org/amateur/telemetry"
    SONDEHUB_AMATEUR_STATION_POSITION_URL = "https://api.v2.sondehub.org/amateur/listeners"

    def __init__(
        self,
        uploader_callsign,
        uploader_position = None,
        uploader_radio = None,
        uploader_antenna = None,
        software_name = None,
        software_version = None,
        upload_rate=2,
        upload_timeout=20,
        upload_retries=5,
        developer_mode=False
    ):
        """ Initialise and start a Sondehub (Amateur) uploader
        
        Mandatory Args:
            uploader_callsign (str): Callsign/name of the uploader.

        Optional Args:
            uploader_position (list): Uploader position as [lat, lon, alt]
            uploader_radio (str): Information on the Uploader's radio.
            uploader_antenna (str): Information on the Uploader's antenna.
            software_name (str): Software name information. If this is provided, software_version must also be provided.
            software_version (str): Software version number, e.g. "0.1.2"
            upload_rate (int): How often to upload batches of data.
            upload_timeout (int): Upload timeout (seconds)
            upload_retries (int): Upload retries
            developer_mode (bool): If set to true, packets will be discarded when they enter the Sondehub DB.
        """

        self.upload_rate = upload_rate
        self.upload_timeout = upload_timeout
        self.upload_retries = upload_retries
        self.developer_mode = developer_mode

        # User information
        self.uploader_callsign = str(uploader_callsign)
        # Optional User Information
        if uploader_position:
            if (type(uploader_position) == list) and (len(uploader_position) ==3):
                self.uploader_position = uploader_position
            else:
                raise ValueError("Invalid uploader position supplied, must be a list with 3 (lat, lon, alt) elements.")
        else:
            self.uploader_position = None
        self.uploader_radio = uploader_radio
        self.uploader_antenna = uploader_antenna

        if software_name:
            # User has supplied a software name, they must also supply a version string
            if not software_version:
                raise ValueError("software_name provided, but no software_version provided.")

            self.software_name = str(software_name)
            self.software_version = str(software_version)
        else:
            self.software_name = "pysondehub"
            self.software_version = sondehub.__version__

        self.software_combined_name = f"{self.software_name}-{self.software_version}"

        # Input Queue.
        self.input_queue = Queue()

        # Start processing the input queue.
        self.input_processing_running = True
        self.input_process_thread = Thread(target=self.process_queue)
        self.input_process_thread.start()


    def add_telemetry(self,
        # Mandatory fields.
        payload_callsign,
        timestamp,  # Either as a string, or a datetime object.
        lat,
        lon,
        alt,
        # Optional 'standard' telemetry fields.
        frame=None,
        time_received=None, # Will be replaced with the current time if not provided.
        sats=None,
        batt=None,
        temp=None,
        humidity=None,
        pressure=None,
        vel_h=None,
        vel_v=None,
        heading=None,
        tx_frequency=None,
        # Optional metadata fields
        modulation=None,
        snr=None,
        frequency=None,
        rssi=None,

        # Per-telemetry-packet Uploader information
        uploader_callsign=None,
        uploader_position=None,
        uploader_antenna=None,
        uploader_radio=None,

        # Any custom fields can be included fields
        extra_fields = {},
    ):
        """
        Add a datapoint of telemetry to the upload queue
        """

        # Output dictionary.
        output = {}

        if self.developer_mode:
            output['dev'] = True

        # Mandatory fields:
        #   Payload callsign
        output['payload_callsign'] = str(payload_callsign)

        #   Timestamp
        if type(timestamp) == datetime.datetime:
            # User has provided a datetime object - we just use this as-is.
            _datetime = timestamp
        else:
            # Try and parse the timestamp as a string.
            # Detect if the user has provider a date:
            _temp_dt = parse(timestamp, default=datetime.datetime(1900,1,1,1,1,1))
            if _temp_dt.year == 1900:
                # User has provided a timestamp with just HH:MM:SS fields.
                # Pass it through fix_datetime
                _datetime = fix_datetime(timestamp)
            else:
                # User has provided a full date/timestamp
                _datetime = _temp_dt
        # Add the datetime to the dictionary.
        output['datetime'] = _datetime.strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        
        #   Lat/Lon/Alt
        output['lat'] = float(lat)
        output['lon'] = float(lon)
        output['alt'] = float(alt)

        #   Drop packets with null lat and lon.
        if (output['lat'] == 0.0) and (output['lon'] == 0.0):
            self.log_warning("Lat/Lon both 0.0 - dropping packet")
            return

        # Packet received time
        if time_received:
            if type(time_received) == datetime.datetime:
                # Provided as a datetime object.
                output['time_received'] = time_received.strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
            else:
                # Provided as a string, parse it and add.
                output['time_received'] = parse(time_received).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        else:
            output['time_received'] = datetime.datetime.utcnow().strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )

        # Optional standard fields.
        if frame:
            output['frame'] = int(frame)

        if sats:
            output['sats'] = int(sats)
            if output["sats"] == 0:
                self.log_error("Satellites field provided, and is 0. Not uploading due to potentially inaccurate position.")
                return
        
        if batt:
            output['batt'] = float(batt)

        if temp:
            output['temp'] = float(temp)

        if humidity:
            output['humdity'] = float(humidity)

        if pressure:
            output['pressure'] = float(pressure)
        
        if vel_v:
            output['vel_v'] = float(vel_v)

        if vel_h:
            output['vel_h'] = float(vel_h)

        if heading:
            output['heading'] = float(heading)

        if tx_frequency:
            output['tx_frequency'] = float(tx_frequency)

        # Optional Metadata fields.
        if modulation:
            output['modulation'] = str(modulation)

        if snr:
            output['snr'] = float(snr)
        
        if frequency:
            output['frequency'] = float(frequency)
        
        if rssi:
            output['rssi'] = float(rssi)
        
        # Per-Packet Uploader Information
        if uploader_callsign:
            # Per-packet uploader information has been provided.
            output['uploader_callsign'] = str(uploader_callsign)

            # Check for any other information.
            if uploader_position:
                # Uploader position has been provided with the telemetry, check it's ok.
                if (type(uploader_position) == list) and (len(uploader_position) == 3):
                    output['uploader_position'] = uploader_position
                else:
                    raise ValueError("Invalid uploader position supplied, must be a list with 3 (lat, lon, alt) elements.")

            if uploader_radio:
                output['uploader_radio'] = str(uploader_radio)

            if uploader_antenna:
                output['uploader_antenna'] = str(uploader_antenna)

        else:
            # No per-packet information - use the information provided on object instantiation.
            output['uploader_callsign'] = self.uploader_callsign

            if self.uploader_position:
                output['uploader_position'] = self.uploader_position
            
            if self.uploader_radio:
                output['uploader_radio'] = str(self.uploader_radio)

            if self.uploader_antenna:
                output['uploader_antenna'] = str(self.uploader_antenna)

        
        # Any extra telemetry fields.
        if type(extra_fields) == dict:
            # Add each supplied field into the output, as long as it is not already present.
            for _field in extra_fields:
                if _field not in output:
                    output[_field] = extra_fields[_field]

        # Add software details
        output["software_name"] = self.software_name
        output["software_version"] = self.software_version

        
        logging.debug(f"Sondehub Amateur Uploader - Generated Packet: {str(output)}")

        # Finally, add the data to the queue if we are running.
        if self.input_processing_running:
            self.input_queue.put(output)
        else:
            self.log_debug("Processing not running, discarding.")


        return


    def add_dict(self, telemetry):
        """ 
        Add a dictionary of telemetry to the input queue. 

        Note that there is no checking of the content of this dictionary.
        Use the add_telemetry function as a guide for what must be included.

        Args:
            telemetry (dict): Telemetry dictionary to add to the input queue.
        """

        # Add it to the queue if we are running.
        if self.input_processing_running:
            self.input_queue.put(telemetry)
        else:
            self.log_debug("Processing not running, discarding.")


    def process_queue(self):
        """ Process data from the input queue, and write telemetry to log files.
        """
        self.log_info("Started Sondehub Amateur Uploader Thread.")

        while self.input_processing_running:

            # Process everything in the queue.
            _to_upload = []

            while self.input_queue.qsize() > 0:
                try:
                    _to_upload.append(self.input_queue.get_nowait())
                except Exception as e:
                    self.log_error("Error grabbing telemetry from queue - %s" % str(e))

            # Upload data!
            if len(_to_upload) > 0:
                self.upload_telemetry(_to_upload)


            # Sleep while waiting for some new data.
            for i in range(int(self.upload_rate)):
                time.sleep(1)
                if self.input_processing_running == False:
                    break

        self.log_info("Stopped Sondehub Amateur Uploader Thread.")


    def upload_telemetry(self, telem_list):
        """ Upload an list of telemetry data to Sondehub """

        _data_len = len(telem_list)

        try:
            _start_time = time.time()
            _telem_json = json.dumps(telem_list).encode("utf-8")
            logging.debug(f"Sondehub Amateur Uploader - Generated Packet: {str(_telem_json)}")
            _compressed_payload = gzip.compress(_telem_json)
        except Exception as e:
            self.log_error(
                "Error serialising and compressing telemetry list for upload - %s"
                % str(e)
            )
            return

        _compression_time = time.time() - _start_time
        self.log_debug(
            "Pre-compression: %d bytes, post: %d bytes. %.1f %% compression ratio, in %.1f s"
            % (
                len(_telem_json),
                len(_compressed_payload),
                (len(_compressed_payload) / len(_telem_json)) * 100,
                _compression_time,
            )
        )

        _retries = 0
        _upload_success = False

        _start_time = time.time()

        while _retries < self.upload_retries:
            # Run the request.
            try:
                headers = {
                    "User-Agent": "pysondehub-" + sondehub.__version__,
                    "Content-Encoding": "gzip",
                    "Content-Type": "application/json",
                    "Date": formatdate(timeval=None, localtime=False, usegmt=True),
                }
                logging.debug(f"Sondehub Amateur Uploader - Upload Headers: {str(headers)}")
                _req = requests.put(
                    self.SONDEHUB_AMATEUR_URL,
                    _compressed_payload,
                    # TODO: Revisit this second timeout value.
                    timeout=(self.upload_timeout, 6.1),
                    headers=headers,
                )
            except Exception as e:
                self.log_error("Upload Failed: %s" % str(e))
                return

            if _req.status_code == 200:
                # 200 is the only status code that we accept.
                _upload_time = time.time() - _start_time
                self.log_info(
                    "Uploaded %d telemetry packets to Sondehub Amateur in %.1f seconds."
                    % (_data_len, _upload_time)
                )
                _upload_success = True
                break

            elif _req.status_code == 500:
                # Server Error, Retry.
                self.log_debug(
                    "Error uploading to Sondehub Amateur. Status Code: %d %s."
                    % (_req.status_code, _req.text)
                )
                _retries += 1
                continue

            else:
                self.log_error(
                    "Error uploading to Sondehub Amateur. Status Code: %d %s."
                    % (_req.status_code, _req.text)
                )
                break

        if not _upload_success:
            self.log_error("Upload failed after %d retries" % (_retries))


    def upload_station_position(
        self,
        callsign,
        position,
        uploader_radio="",
        uploader_antenna="",
        contact_email="",
        mobile=False,
        ):
        """ 
        Upload station position information to the SondeHub-Amateur Database.
        This is distinct from the station information sent along with telemetry,
        in that it results in a station icon being shown on the tracker map for
        ~12 hours after the upload.
        
        If 'mobile' is set to True, then the station will appear as a chase-car
        instead. In this case, positions should be uploaded at much more regular 
        intervals to reflect the movement of the chase car.

        This uses the PUT /amateur/listeners API described here:
        https://github.com/projecthorus/sondehub-infra/wiki/API-(Beta)
        """

        _callsign = str(callsign)
        _radio = str(uploader_radio)
        _antenna = str(uploader_antenna)
        _contact_email = str(contact_email)

        if (type(position) == list) and (len(position) == 3):
            _user_position = position
        else:
            raise ValueError("Invalid uploader position supplied, must be a list with 3 (lat, lon, alt) elements.")

        _position = {
            "software_name": self.software_name,
            "software_version": self.software_version,
            "uploader_callsign": _callsign,
            "uploader_position": _user_position,
            "uploader_radio": _radio,
            "uploader_antenna": _antenna,
            "uploader_contact_email": _contact_email,
            "mobile": mobile, 
            "dev": self.developer_mode
        }

        logging.debug(f"Sondehub Amateur Uploader - Generated Station Position Packet: {str(_position)}")

        _retries = 0
        _upload_success = False

        _start_time = time.time()

        while _retries < self.upload_retries:
            # Run the request.
            try:
                headers = {
                    "User-Agent": "pysondehub-" + sondehub.__version__,
                    "Content-Type": "application/json",
                    "Date": formatdate(timeval=None, localtime=False, usegmt=True),
                }
                _req = requests.put(
                    self.SONDEHUB_AMATEUR_STATION_POSITION_URL,
                    json=_position,
                    # TODO: Revisit this second timeout value.
                    timeout=(self.upload_timeout, 6.1),
                    headers=headers,
                )
            except Exception as e:
                self.log_error("Upload Failed: %s" % str(e))
                return

            if _req.status_code == 200:
                # 200 is the only status code that we accept.
                _upload_time = time.time() - _start_time
                self.log_info("Uploaded station information to Sondehub.")
                _upload_success = True
                break

            elif _req.status_code == 500:
                # Server Error, Retry.
                _retries += 1
                continue

            elif _req.status_code == 404:
                # API doesn't exist yet!
                self.log_debug("Sondehub Amateur position upload API not implemented yet!")
                _upload_success = True
                break

            else:
                self.log_error(
                    "Error uploading station information to Sondehub. Status Code: %d %s."
                    % (_req.status_code, _req.text)
                )
                break

        if not _upload_success:
            self.log_error(
                "Station information upload failed after %d retries" % (_retries)
            )
            self.log_debug(f"Attempted to upload {json.dumps(_position)}")

        self.last_user_position_upload = time.time()

    def close(self):
        """ Close input processing thread. """
        self.input_processing_running = False

    def running(self):
        """ Check if the uploader thread is running. 

        Returns:
            bool: True if the uploader thread is running.
        """
        return self.input_processing_running

    def log_debug(self, line):
        """ Helper function to log a debug message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.debug("Sondehub Amateur Uploader - %s" % line)

    def log_info(self, line):
        """ Helper function to log an informational message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.info("Sondehub Amateur Uploader - %s" % line)

    def log_error(self, line):
        """ Helper function to log an error message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.error("Sondehub Amateur Uploader - %s" % line)

    def log_warning(self, line):
        """ Helper function to log an error message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.warning("Sondehub Amateur Uploader - %s" % line)


if __name__ == "__main__":
    # Test Script for Uploader Class
    logging.basicConfig(format="%(asctime)s %(levelname)s:%(message)s", level=logging.DEBUG)

    _test = Uploader(
        "N0CALL-DEV-TESTING",
        uploader_position=[0.1,0.1,0],
        uploader_radio="Testing pysondehub",
        uploader_antenna="Testing pysondehub",
        developer_mode=True
    )
    _test.upload_station_position(
        "N0CALL-DEV-TESTING",
        [0.1,0.1, 0],
        uploader_radio="Testing pysondehub radio",
        uploader_antenna="Testing pysondehub antenna"
    )
    _test.upload_station_position(
        "N0CALL-DEV2-TESTING",
        [-0.1, -0.1, 0.0],
        mobile=True
    )

    _temp_date = datetime.datetime.utcnow()
    _date_str = _temp_date.strftime("%H:%M:%S")

    _test.add_telemetry(
        "VK5QI-DEV-TEST",
        _date_str,
        -0.1,
        0.1,
        10000,
        frame=123,
        sats=10,
        batt=3.14159,
        temp=-42.0,
        pressure=1001.23,
        humidity=99,
        vel_v=-42.0,
        vel_h=100.0,
        heading=359.0,
        snr=55.0,
        frequency=434.123,
        rssi=-123.0,
        modulation="Test",
        extra_fields={"my_field_1":5, "my_field_2":"foo", "my_field_3":-123.456},
        uploader_callsign="N0CALL-DEV2-TESTING",
        uploader_position=[0.15,0.15,0]
    )
    # Allow time for the packet to be uploaded.
    time.sleep(5)
    # Close the uploader
    _test.close()
