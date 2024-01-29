# main.py 
#
# written by: Oliver Cordes 2024-01-20
# changed by: Oliver Cordes 2024-01-22


from dotenv import load_dotenv
import os, sys
import logging

import requests

import argparse

__version__ = '0.99.0'

inverter_limit = '.last_inverter_limit'


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
        power = data['StatusSNS']['ENERGY']['Power_cur']

        return power, msg
    else:
        msg = f'Error: Unknown power type {power_type}'
        return None, msg


def ahoy_get_power_limit():
    """
    Get the current power limit from the ahoy DTU server
    """
    AHOY_SERVER = os.getenv('AHOY_DTU_URL')
    INVERTER = os.getenv('AHOY_DTU_INVERTER')

    URL = f'{AHOY_SERVER}/api/inverter/id/{INVERTER}'
    
    msg = 'OK'

    try:
        response = requests.get(URL,timeout=5)
    except requests.exceptions.Timeout:
        msg = 'Error: Could not get power data (timeout)'
        logging.error(msg)
        return None, None

    if response.status_code != 200:
        msg = f'Error: Could not get power data (error={response.status_code})'
        logging.error(msg)
        return None, None

    # convert data
    data = response.json()

    # get the power information
    power = int(data['ch'][0][2])

    limit = 0
    max_power = int(data['max_pwr'])


    if data['power_limit_ack'] and (data['power_limit_read'] < 65000):
        limit_read = int(data['power_limit_read']) / 100
        limit = int(max_power * limit_read) 

    if limit > power:
        limit = power

    return limit, max_power


def ahoy_set_power_limit(limit):

    old_limit = load_limit_from_file()

    if limit == old_limit:
        msg = f'Limit is already set to {limit} W'
        logging.info(msg)
        return False

    cmd = {
       "id":  int(os.getenv('AHOY_DTU_INVERTER')),
       "cmd": 'limit_nonpersistent_absolute',
       "val": limit,
    }

    AHOY_SERVER = os.getenv('AHOY_DTU_URL')

    URL = f'{AHOY_SERVER}/api/ctrl'

    #print(URL)
    #print(cmd)

    r = requests.post(URL, json=cmd)
    
    if r.status_code == 200:
        msg = f'Set inverter Limit to {limit} W'
        logging.info(msg)

        # save the limit to a file
        save_limit_to_file(limit)
    else:
        msg = f'Status Code: {r.status_code}, Limit not set to {limit} W'
        logging.error(msg)

    return True


def doit(args):
    if args.manuallimit > -1:
        # overwrite the automatic limit calculation
        new_limit = args.manuallimit
    else:
        # automatic limit calculation
        # get the current power consumption

        mp, error_msg = get_main_power()

        if mp is None:
            print('No main power defined: {error_msg}') 
            sys.exit(1)

        print(f'current power consumption: {mp} W')
        logging.info(f'current power consumption: {mp} W')

        power_limit, max_power = ahoy_get_power_limit()

        if power_limit is None:
            print('No power limit defined: {error_msg}') 
            sys.exit(1)

        print(f'current inverter power:    {power_limit} W  (max power: {max_power} W)')
        logging.info(f'current inverter power: {power_limit} W  (max power: {max_power} W)')


        if mp > 0:
            # no energy is served to the grid

            if int(os.getenv('MAX_VALUE')) > 0:
                new_limit = int(os.getenv('MAX_VALUE'))
            else:
                if args.maxpower > 0:
                    new_limit = args.maxpower
                else:
                    new_limit = max_power

        else:
            # energy is served to the grid

            zero = int(os.getenv('ZERO'))

            if args.zero != 65535:  # overwrite the zero value if set
                zero = args.zero

            # calculate the limit for zeroenergy
            new_limit = mp + power_limit - zero

            # if we have a negative value, serve no energy to the grid
            if new_limit < 0:
                new_limit = 0   

    if args.simulate:
        print(f'Simulate new inverter limit: {new_limit} W') 
        logging.info(f'Simulate new inverter limit: {new_limit} W')
    else:   
        res = ahoy_set_power_limit(new_limit)
        if res:
            print(f'Set new inverter limit:    {new_limit} W') 
            logging.info(f'Set new inverter limit: {new_limit} W')
        else:
            print(f'Inverter limit is not changed!')

    
# main

parser = argparse.ArgumentParser(
    prog='zeroenergy',    
    description='Implementing zero power to the power grid (Nulleinspeisung)',
    epilog='(C) 2024 Oliver Cordes')


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

doit(args)
logging.info('Finished')

