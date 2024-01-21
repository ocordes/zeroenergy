# main.py 
#
# written by: Oliver Cordes 2024-01-20
# changed by: Oliver Cordes 2024-01-20


from dotenv import load_dotenv
import os, sys

import requests

# load .env file
load_dotenv()


def get_main_power():
    power_type = os.getenv('MAIN_POWER')
    
    if power_type == 'tasmota':

        BASE_URL = os.getenv('TASMOTA_URL')
        URL = f'{BASE_URL}/cm?cmnd=status%2010'

        try:
            response = requests.get(URL,timeout=5)
        except requests.exceptions.Timeout:
            print('Error: Could not get power data (timeout)')
            return None 
        

        if response.status_code != 200:
            print(f'Error: Could not get power data (error={response.status_code})')
            return None
        
        data = response.json()
        power = data['StatusSNS']['ENERGY']['Power_cur']

        return power
    else:
        return None


def ahoy_get_power_limit():

    AHOY_SERVER = os.getenv('AHOY_DTU_URL')
    INVERTER = os.getenv('AHOY_DTU_INVERTER')

    URL = f'{AHOY_SERVER}/api/inverter/id/{INVERTER}'
    
    try:
        response = requests.get(URL,timeout=5)
    except requests.exceptions.Timeout:
        print('Error: Could not get power data (timeout)')
        return None 

    if response.status_code != 200:
        print(f'Error: Could not get power data (error={response.status_code})')
        return None

    # convert data
    data = response.json()

    # get the power information
    power = int(data['ch'][0][2])

    limit = 0
    if data['power_limit_ack'] and (data['power_limit_read'] < 65000):
        max_power = int(data['max_pwr'])
        limit_read = int(data['power_limit_read']) / 100
        limit = int(max_power * limit_read) 

    if limit > power:
        limit = power

    return limit


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


# main
mp = get_main_power()

if mp is None:
    print('No main power defined') 
    sys.exit(1)

print(mp)

power_limit = ahoy_get_power_limit()

print(power_limit)


new_limit = mp + power_limit + 5


print(new_limit)

if new_limit < 0:
    new_limit = 0

print('new limit: ', new_limit) 

ahoy_set_power_limit(400)
#ahoy_set_power_limit(new_limit)