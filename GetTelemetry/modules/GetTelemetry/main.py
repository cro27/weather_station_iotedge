# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

import json
import getopt
import sys
import random
import time
import sys
import re
from datetime import datetime
from dateutil import tz
from ast import literal_eval
from subprocess import call
# pylint: disable=E0401
from pywws import weatherstation
import logging
import iothub_client
# pylint: disable=E0611
from iothub_client import IoTHubModuleClient, IoTHubClientError, IoTHubTransportProvider
from iothub_client import IoTHubMessage, IoTHubMessageDispositionResult, IoTHubError

# messageTimeout - the maximum time in milliseconds until a message times out.
# The timeout period starts at IoTHubModuleClient.send_event_async.
# By default, messages do not expire.
MESSAGE_TIMEOUT = 10000

# global counters
RECEIVE_CALLBACKS = 0
SEND_CALLBACKS = 0
TWIN_CALLBACKS = 0
MESSAGE_COUNT = 0

# set deviceid
DeviceID = "<Device Name>"

# Choose HTTP, AMQP or MQTT as transport protocol.  Currently only MQTT is supported.
PROTOCOL = IoTHubTransportProvider.MQTT

# Callback received when the message that we're forwarding is processed.
def send_confirmation_callback(message, result, user_context):
    global SEND_CALLBACKS
    print ( "Confirmation[%d] received for message with result = %s" % (user_context, result) )
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    print ( "    Properties: %s" % key_value_pair )
    SEND_CALLBACKS += 1
    print ( "    Total calls confirmed: %d" % SEND_CALLBACKS )


# receive_message_callback is invoked when an incoming message arrives on the specified 
# input queue (in the case of this sample, "input1").  Because this is a filter module, 
# we will forward this message onto the "output1" queue.
def receive_message_callback(message, hubManager):
    global RECEIVE_CALLBACKS
    message_buffer = message.get_bytearray()
    size = len(message_buffer)
    print ( "    Data: <<<%s>>> & Size=%d" % (message_buffer[:size].decode('utf-8'), size) )
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    print ( "    Properties: %s" % key_value_pair )
    RECEIVE_CALLBACKS += 1
    print ( "    Total calls received: %d" % RECEIVE_CALLBACKS )
    hubManager.forward_event_to_output("output1", message, 0)
    return IoTHubMessageDispositionResult.ACCEPTED

# Interpret wind direction
def wind_direction(dir_num):
    if dir_num == 0:
        return 'S'
    elif dir_num == 1: 
        return 'SSW'
    elif dir_num == 2:
        return 'SW'
    elif dir_num == 3:
        return 'WSW'
    elif dir_num == 4:
        return 'W'
    elif dir_num == 5:
        return 'WNW'
    elif dir_num == 6:
        return 'NW'
    elif dir_num == 7:
        return 'NNW'
    elif dir_num == 8:
        return 'N'
    elif dir_num == 9: 
        return 'NNE'
    elif dir_num == 10:
        return 'NE'
    elif dir_num == 11:
        return 'ENE'
    elif dir_num == 12:
        return 'E'
    elif dir_num == 13:
        return 'ESE'
    elif dir_num == 14:
        return 'SE'
    elif dir_num == 15:
        return 'SSE'

# Check for weather station connectivity, format the data and send to IoT Hub
def get_reading():
    global DeviceID
    ws = weatherstation.WeatherStation()
    # format message 
    MSG_TXT = "{\"deviceId\": \"%s\",\"rec_time\": \"%s\",\"hum_out\": %d,\"temp_out\": %.1f,\"hum_in\": %d,\"temp_in\": %.1f, \"abs_pres\": %.1f,\"wind_gust\": %.1f,\"wind_avg\": %.1f,\"wind_dir\": %d,\"wind_pos\": \"%s\",\"rain_total\": %.1f}"
    for data, ptr, logged in ws.live_data():
        record_time_local = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
        print(record_time_local)
        ws_conn = data['status']['lost_connection']
		# Check for lost connection
        if ws_conn == True:
            print("Lost Connection to Weather Station")
            break
        # Check for Null Data
        if ws_conn == None:
            print("No Data Returned From Weather Station")
            break
        # Connection is OK so process the data
        hum_out = data['hum_out']
        temp_out = data['temp_out']
        hum_in = data['hum_in']
        temp_in = data['temp_in']
        abs_pres = data['abs_pressure']+9.6 
        wind_gust = data['wind_gust']*3.6  
        wind_avg = data['wind_ave']*3.6    
        wind_dir = data['wind_dir']
        wind_pos = wind_direction(wind_dir)
        rain = data['rain']
        msg = MSG_TXT % (
            DeviceID,
            record_time_local,
            hum_out,
            temp_out,
            hum_in,
            temp_in,
            abs_pres,
            wind_gust,
            wind_avg,
            wind_dir,
            wind_pos,
            rain)
        break
    if ws_conn == False:
        if hum_out <= 1050:
            return msg

class HubManager(object):

    def __init__(
            self,
            protocol=IoTHubTransportProvider.MQTT):
        self.client_protocol = protocol
        self.client = IoTHubModuleClient()
        self.client.create_from_environment(protocol)

        # set the time until a message times out
        self.client.set_option("messageTimeout", MESSAGE_TIMEOUT)
        
        # sets the callback when a message arrives on "input1" queue.  Messages sent to 
        # other inputs or to the default will be silently discarded.
        self.client.set_message_callback("input1", receive_message_callback, self)

    # Forwards the message received onto the next stage in the process.
    def forward_event_to_output(self, outputQueueName, event, send_context):
        self.client.send_event_async(
            outputQueueName, event, send_confirmation_callback, send_context)
    
    def SendData(self, msg):
        global MESSAGE_COUNT
        record_time_local = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
        print("\nsending message %d at %s" % (MESSAGE_COUNT, record_time_local))
        print(msg)
        message=IoTHubMessage(msg)
        message.message_id = "message_%d" % MESSAGE_COUNT
        message.correlation_id = "correlation_%d" % MESSAGE_COUNT
        self.client.send_event_async("output1", message, send_confirmation_callback, 0)
        print("finished sending message %d\n" %(MESSAGE_COUNT))

def main(protocol):
    try:
        print ( "\nPython %s\n" % sys.version )
        print ( "IoT Hub Client for Python" )

        hub_manager = HubManager(protocol)

        print ( "Starting the IoT Hub Python sample using protocol %s..." % hub_manager.client_protocol )
        #print ( "The sample is now waiting for messages and will indefinitely.  Press Ctrl-C to exit. ")

        while True:
            global MESSAGE_COUNT
            msg=get_reading()
            hub_manager.SendData(msg)
            MESSAGE_COUNT += 1
            time.sleep(10)

    except IoTHubError as iothub_error:
        print ( "Unexpected error %s from IoTHub" % iothub_error )
        return
    except KeyboardInterrupt:
        print ( "IoTHubModuleClient sample stopped" )

if __name__ == '__main__':
    main(PROTOCOL)
