# main.py 
#
# written by: Oliver Cordes 2024-01-20
# changed by: Oliver Cordes 2024-01-21


from dotenv import load_dotenv
import os, sys

import requests

import argparse

__version__ = '0.99.0'

# load .env file
load_dotenv()


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
        return None, None, msg 

    if response.status_code != 200:
        msg = f'Error: Could not get power data (error={response.status_code})'
        return None, None,  msg

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

    return limit, max_power, msg


def ahoy_set_power_limit(limit):
    cmd = {
       "id":  int(os.getenv('AHOY_DTU_INVERTER')),
       "cmd": 'limit_nonpersistent_absolute',
       "val": limit,
    }

    AHOY_SERVER = os.getenv('AHOY_DTU_URL')

    URL = f'{AHOY_SERVER}/api/ctrl'

    print(URL)
    print(cmd)

    r = requests.post(URL, json=cmd)
    
    print(f"Status Code: {r.status_code}") #, Response: {r.json()}")

    return


def doit(args):
    mp, error_msg = get_main_power()

    if mp is None:
        print('No main power defined: {error_msg}') 
        sys.exit(1)

    print(f'current power consumption: {mp} W')

    power_limit, max_power, error_msg = ahoy_get_power_limit()

    if power_limit is None:
        print('No power limit defined: {error_msg}') 
        sys.exit(1)

    print(f'current inverter power:    {power_limit} W  (max power: {max_power} W)')


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
        # calculate the limit for zeroenergy
        new_limit = mp + power_limit - zero

        # if we have a negative value, serve no energy to the grid
        if new_limit < 0:
            new_limit = 0   


    print(f'new inverter limit:        {new_limit} W') 

    #ahoy_set_power_limit(400)
    #ahoy_set_power_limit(new_limit)


# main

parser = argparse.ArgumentParser(
    prog='zeroenergy',    
    description='Implementing zero power to the power grid (Nulleinspeisung)',
    epilog='(C) 2024 Oliver Cordes')


parser.add_argument('-v', '--verbose',
                    action='store_true')  # on/off flag
parser.add_argument('--version', action='version', version=f'%(prog)s {__version__} (C) 2024 Oliver Cordes')
parser.add_argument('-m', '--maxpower', action='store', type=int, default=-1)                   

args = parser.parse_args()

doit(args)


