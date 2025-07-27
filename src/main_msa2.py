# main.py 
#
# written by: Oliver Cordes 2025-07-24
# changed by: Oliver Cordes 2025-07-26


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
battery_grid_power = None

battery_state = { 'soc': None, 'grid_on_p': None}

battery_power_set = 0
battery_power_set_prev = 0  

battery_set_min = -1000   # minimum power set to the battery, charging
battery_set_max = 200    # maximum power set to the battery, discharging
power_high_consumption = 1000  # power consumption above this value will set the battery power set to 0 W

battery_zero_buffer = 10  # buffer to avoid oscillation, use more grid power

battery_total_in = 0 # total power set to the battery, charging
battery_total_out = 0  # total power set to the battery, discharging

# day of today, used to reset the total power counters
# this is used to reset the counters at midnight
day_of_today = 0
day_of_today_prev = 0

# load .env file
load_dotenv()

# read the environment variables
battery_set_max = int(os.getenv('BATTERY_SET_MAX', battery_set_max))
battery_set_min = int(os.getenv('BATTERY_SET_MIN', battery_set_min))

power_high_consumption = int(os.getenv('POWER_HIGH_CONSUMPTION', power_high_consumption))

# -------

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



def get_main_power_cycle(update_cycle=30):
    """
    Get the current power from the main power source in a loop
    """
    #print(f'Get main power every {update_cycle} seconds')

    nr_of_cycles = int(os.getenv('NR_POWER_READINGS', 5))
    values = []
    small_cycle = update_cycle / nr_of_cycles
    for i in range(nr_of_cycles):
        power, msg = get_main_power()
        if power is not None:
            #print(f'Current main power: {power} W')
            values.append(power)
        else:
            print(msg)
        time.sleep(small_cycle)  # wait for the next cycle

    #print(values)
    return sum(values)/len(values), msg





def doit(args):
    global battery_power_set, battery_power_set_prev
    global day_of_today, day_of_today_prev
    global battery_total_in, battery_total_out

    update_cycle = 30  # seconds

    update_cycle = int(os.getenv('UPDATE_CYCLE', update_cycle))
    
    mqtt_topic = os.getenv('MQTT_TOPIC', 'homeassistant/number/MSA-280024370560/power_ctrl/set')


    time.sleep(5)  # wait for MQTT connection to be established and messages to be received

    print('doit algorithm:')
    print(f'  BATTERY_SET_MAX: {battery_set_max} W')
    print(f'  BATTERY_SET_MIN: {battery_set_min} W')

    bat_grid_power = battery_state['grid_on_p']
    print(f'  BATTERY_ON_GRID_POWER: {bat_grid_power} W')

    if bat_grid_power is not None:
        battery_power_set = bat_grid_power
        battery_power_set_prev = bat_grid_power

    while True:
        # print the current time
        time_now = time.localtime()
        print('----', time.strftime('%Y-%m-%d %H:%M:%S', time_now), '----')

        day_of_today = time_now.tm_mday
        if (day_of_today != day_of_today_prev) and (day_of_today_prev != 0):
            # reset the total power counters at midnight
            print(f'Resetting total power counters for today!')
            battery_total_in = 0
            battery_total_out = 0
            day_of_today_prev = day_of_today

        battery_soc = battery_state['soc']
        battery_grid_power = battery_state['grid_on_p']


        # get the current power consumption
        mp, error_msg = get_main_power_cycle(update_cycle=update_cycle)

        if mp is None:
            print(f'No main power defined: {error_msg}') 
            sys.exit(1)

        print(f'current power consumption: {mp} W')
        logging.info(f'current power consumption: {mp} W')

        if battery_soc is not None:
            print(f'current battery state of charge: {battery_soc}%')
            
        
        if battery_grid_power is not None:
            print(f'current battery grid power: {battery_grid_power} W')

        # crosscheck the battery power set with the current grid power
        if battery_grid_power is not None:
            if battery_grid_power != battery_power_set:
                print(f'Battery grid power {battery_grid_power} W does not match battery power set {battery_power_set} W, updating power set')
                battery_power_set = battery_grid_power
                battery_power_set_prev = battery_grid_power

        # calculate the new power set
        new_power_set = int(battery_power_set + mp)

        print(f'current battery power set: {new_power_set} W')

        # shaping the new power set

        # phase 1: check if the new power set is within the limits
        if new_power_set > battery_set_max:
            new_power_set = battery_set_max
        elif new_power_set < battery_set_min:
            new_power_set = battery_set_min


        #  phase 2: check if we are falling or rising
        if new_power_set > battery_power_set_prev:
            # we are rising, so check charging or discharging
            if new_power_set < 0:
                # leave it as it is, we are charging
                pass
            else:
                # leave it as it is, we are discharging
                pass
        if new_power_set < battery_power_set_prev:
            # we are falling
            new_power_set = new_power_set - battery_zero_buffer


        # phase 3: check if the power consumption is far to high
        if mp > power_high_consumption:
            print(f'Power consumption is too high, setting power set to 0 W')
            logging.warning(f'Power consumption is too high, setting power set to 0 W')
            new_power_set = 0


        print(f'shaped new power set: {new_power_set} W')
        #if new_power_set >  0:
        #    new_power_set = 0

        if (new_power_set < 0) and (battery_soc is not None) and (battery_soc >= 99.9):
            print(f'Battery is full, setting power set to 0 W')
            logging.warning(f'Battery is full!')    
            new_power_set = 0

        if (new_power_set > 0) and (battery_soc is not None) and (battery_soc <= 10.1):
            print(f'Battery is empty, setting power set to 0 W')
            logging.warning(f'Battery is empty!')    
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

            if new_power_set > 0:
                battery_total_out += update_cycle * new_power_set / 3600
            else:
                battery_total_in += update_cycle * abs(new_power_set) / 3600

            logging.info(f'Total IO battery: {battery_total_in:.1f} Wh (IN), {battery_total_out:.1f} Wh (OUT), SOC: {battery_soc:.1f}%')

        else:
            print('Nothing to do, powerset for battery is zero!')
            battery_power_set_prev = 0
            battery_power_set =  0
        

        # wait for the next time period
        #time.sleep(update_cycle)
    

    
def on_message(client, userdata, message):
    global battery_soc, batter_grid_power

    # userdata is the structure we choose to provide, here it's a list()
    #userdata.append(message.payload)
    payload = json.loads(message.payload.decode('utf-8'))

    #print(f"Received message: {payload} {type(payload)}")

    battery_soc = float(payload['sys_soc'])
    battery_grid_power = float(payload['grid_on_p'])

    #print(battery_soc, battery_grid_power)

    battery_state['soc'] = battery_soc
    battery_state['grid_on_p'] = battery_grid_power


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
                    version=f'%(prog)s {__version__} (C) 2025 Oliver Cordes',
                    help='show the version and exit')
    parser.add_argument('-d', '--debug', action='store_true')
    
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
