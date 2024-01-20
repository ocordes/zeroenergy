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
        response = requests.get(URL,timeout=5)

        print(URL)

        if response.status_code != 200:
            print(f'Error: Could not get power data (error={response.status_code})')
            return None
        
        data = response.json()
        power = data['StatusSNS']['ENERGY']['Power_cur']

        return power
    else:
        return None




# main
mp = get_main_power()

if mp is None:
    print('No main power defined') 
    sys.exit(1)

print(mp)