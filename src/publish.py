import time
import paho.mqtt.client as mqtt

def on_publish(client, userdata, mid, reason_code, properties):
    # reason_code and properties will only be present in MQTTv5. It's always unset in MQTTv3
    try:
        userdata.remove(mid)
    except KeyError:
        print("on_publish() is called with a mid not present in unacked_publish")
        print("This is due to an unavoidable race-condition:")
        print("* publish() return the mid of the message sent.")
        print("* mid from publish() is added to unacked_publish by the main thread")
        print("* on_publish() is called by the loop_start thread")
        print("While unlikely (because on_publish() will be called after a network round-trip),")
        print(" this is a race-condition that COULD happen")
        print("")
        print("The best solution to avoid race-condition is using the msg_info from publish()")
        print("We could also try using a list of acknowledged mid rather than removing from pending list,")
        print("but remember that mid could be re-used !")

unacked_publish = set()
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_publish = on_publish

mqttc.user_data_set(unacked_publish)
#mqttc.connect("mqtt.eclipseprojects.io")
mqttc.connect("192.168.178.63", 1883, 60)
mqttc.loop_start()

# Our application produce some messages
#msg_info = mqttc.publish("paho/test/topic", "my message", qos=1)
msg_info = mqttc.publish(
    "homeassistant/number/MSA-280024370560/power_ctrl/set", "-100", qos=1)

unacked_publish.add(msg_info.mid)

#msg_info2 = mqttc.publish("paho/test/topic", "my message2", qos=1)
#unacked_publish.add(msg_info2.mid)

"""
{"supported_topics": {"quick_state": "homeassistant/sensor/MSA-280024370560/quick/state", "device_state": "homeassistant/sensor/MSA-280024370560/device/state",
                      "system_state": "homeassistant/sensor/MSA-280024370560/system/state", "ems_mode": "homeassistant/select/MSA-280024370560/ems_mode/command", 
                      "power_ctrl": "homeassistant/number/MSA-280024370560/power_ctrl/set"}}
"""




# Wait for all message to be published
while len(unacked_publish):
    time.sleep(0.1)

# Due to race-condition described above, the following way to wait for all publish is safer
msg_info.wait_for_publish()
#msg_info2.wait_for_publish()

mqttc.disconnect()
mqttc.loop_stop()