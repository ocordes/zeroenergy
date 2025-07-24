# main.py 
#
# written by: Oliver Cordes 2025-07-24
# changed by: Oliver Cordes 2025-07-24


from dotenv import load_dotenv
import os, sys

import time
import logging
import json

import requests

import argparse

import mqtt 

__version__ = '0.99.0'

inverter_limit = '.last_inverter_limit'

# battery state
battery_soc = None

battery_power_set = 0
battery_power_set_prev = 0  

battery_set_min = -100   # minimum power set to the battery, charging
battery_set_max = 100    # maximum power set to the battery, discharging


# load .env file
load_dotenv()

def save_limit_to_file(limit):
    """
    Save the current limit to a file
    """
    with open(inverter_limit, 'w') as f:
        f.write(str(limit)+'\n')


def load_limit_from_file():
    """
    Load the current (last) limit from a file
    """
    limit = 0

    if os.path.exists(inverter_limit):
        with open(inverter_limit, 'r') as f:
            limit = int(f.readline())

    return limit


def get_main_power():
    """
    Get the current power from the main power source    
    """
    power_type = os.getenv('MAIN_POWER')
    json_path = os.getenv('TASMOTA_PATH', 'StatusSNS.Energy.Power_cur').strip().split('.')
    if len(json_path) < 3:
        print(f'Error: Invalid TASMOTA_PATH {os.getenv("TASMOTA_PATH")}')
        return None, 'Invalid TASMOTA_PATH'

    
    msg = 'OK'
    if power_type == 'tasmota':

        BASE_URL = os.getenv('TASMOTA_URL')
        URL = f'{BASE_URL}/cm?cmnd=status%2010'

        try:
            response = requests.get(URL,timeout=5)
        except requests.exceptions.Timeout:
            msg = 'Error: Could not get power data (timeout)'
            return None, msg
        

        if response.status_code != 200:
            msg = f'Error: Could not get power data (error={response.status_code})'
            return None, msg
        
        data = response.json()
        #
        # power = data['StatusSNS']['Energy']['Power_cur']
        power = data[json_path[0]][json_path[1]][json_path[2]]

        return power, msg
    else:
        msg = f'Error: Unknown power type {power_type}'
        return None, msg








def doit(args):
    global battery_power_set, battery_power_set_prev
    
    mqtt_topic = os.getenv('MQTT_TOPIC', 'homeassistant/number/MSA-280024370560/power_ctrl/set')

    while True:
        # print the current time
        print('----', time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()), '----')

        # get the current power consumption
        mp, error_msg = get_main_power()

        if mp is None:
            print(f'No main power defined: {error_msg}') 
            sys.exit(1)

        print(f'current power consumption: {mp} W')
        logging.info(f'current power consumption: {mp} W')

        if battery_soc is not None:
            print(f'current battery state of charge: {battery_soc}%')
            logging.info(f'current battery state of charge: {battery_soc}%')
        

        # calculate the new power set
        new_power_set = int(battery_power_set + mp)

        print(f'current battery power set: {new_power_set} W')

        # shaping the new power set
        if new_power_set > max(battery_set_max, args.maxpower):
            new_power_set = max(battery_set_max, args.maxpower)
        elif new_power_set < battery_set_min:
            new_power_set = battery_set_min

        print(f'shaped new power set: {new_power_set} W')
        if new_power_set >  0:
            new_power_set = 0

        if (new_power_set < 0) and (battery_soc is not None) and (battery_soc >= 99.9):
            print(f'Battery is full, setting power set to 0 W')
            logging.warning(f'Battery is full!')    
            new_power_set = 0


        if new_power_set != 0:
            # if the new power set is the same as the previous one, add a small delta to avoid the same value
            if new_power_set == battery_power_set:
                new_power_set = new_power_set - 0.1

            print(f'new power set: {new_power_set} W')
            battery_power_set_prev = battery_power_set
            battery_power_set = new_power_set
            mqtt.mqtt_publish(mqtt_topic, str(new_power_set), qos=1)    
                

            logging.info(f'new power set for battery: {new_power_set} W')
        else:
            print('Nothing to do, powerset for battery is zero!')
            battery_power_set_prev = 0
            battery_power_set =  0
        

        #print('----')
        time.sleep(30)
    

    
def on_message(client, userdata, message):
    global battery_soc

    # userdata is the structure we choose to provide, here it's a list()
    #userdata.append(message.payload)
    payload = json.loads(message.payload.decode('utf-8'))

    #print(f"Received message: {payload} {type(payload)}")

    battery_soc = float(payload['sys_soc'])




# main

if __name__ == '__main__':

    # parse the command line arguments

    parser = argparse.ArgumentParser(
        prog='zeroenergy',    
        description='Implementing zero power to the grid using battery (Nulleinspeisung/Überschussladen)',
        epilog='(C) 2025 Oliver Cordes')


    parser.add_argument('-v', '--verbose',
                    action='store_true', help='enable verbose mode')  # on/off flag
    parser.add_argument('--version', action='version', 
                    version=f'%(prog)s {__version__} (C) 2024 Oliver Cordes',
                    help='show the version and exit')
    parser.add_argument('-m', '--maxpower', action='store', 
                    type=int, default=-1,
                    help="set the maximum power (W) for the inverter")        
    parser.add_argument('-z', '--zero', action='store', 
                    type=int, default=65535,
                    help="set the zero value (W) for the grid")     
    parser.add_argument('-s', '--simulate', action='store_true',
                    help='simulate the setting of the inverter limit')
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('--manuallimit', action='store', 
                    type=int, default=-1,
                    help="set the limit manually (W) for the inverter")     

    args = parser.parse_args()


    if args.debug:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(filename='zeroenergy.log', level=level, format='%(asctime)s %(levelname)s %(message)s')
    logging.info('Started')

    mqtt.mqtt_init(os.getenv('MQTT_HOST', 'localhost'),
                   port=int(os.getenv('MQTT_PORT', 1883)))  

    mqtt.mqtt_subscribe("homeassistant/sensor/MSA-280024370560/quick/state", on_message, qos=1)

    try:
        doit(args)
    except KeyboardInterrupt as e:
        #logging.error(f'Error occurred: {e}')
        pass
    #doit(args)

    mqtt.mqtt_done()
    logging.info('Finished')
    print('Finished')
    sys.exit(0)
