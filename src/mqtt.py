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


def on_subscribe(client, userdata, mid, reason_code_list, properties):
    # Since we subscribed only for a single channel, reason_code_list contains
    # a single entry
    if reason_code_list[0].is_failure:
        print(f"Broker rejected you subscription: {reason_code_list[0]}")
    else:
        print(f"Broker granted the following QoS: {reason_code_list[0].value}")




unacked_publish = set()

mqttc = None


def mqtt_init(host, port=1883, keepalive=60):
    global mqttc, unacked_publish
    # create an MQTT client instance
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                        userdata=unacked_publish)   
    #client_id="zeroenergy", clean_session=True, userdata=unacked_publish)
    
    # set the on_publish callback
    mqttc.on_publish = on_publish

    # set the on_subscribe callback
    mqttc.on_subscribe = on_subscribe
    
    mqttc.user_data_set([])


    # connect to the MQTT broker
    err = mqttc.connect(host, port, keepalive)
    if err != mqtt.MQTT_ERR_SUCCESS:
        print(f"Failed to connect to MQTT broker: {mqttc.error_string(err)}")
        mqttc = None
        return False
    else:
        print(f"Connected to MQTT broker at {host}:{port}")
        mqttc.loop_start()
        return True


def mqtt_publish(topic, payload, qos=1):
    global mqttc, unacked_publish
    # publish a message to the specified topic
    if mqttc is None:
        print("MQTT client is not initialized. Call mqtt_init() first.")
        return

    msg_info = mqttc.publish(topic, payload, qos=qos)
    
    # add the message ID to the unacked_publish set
    unacked_publish.add(msg_info.mid)

    while len(unacked_publish):
        time.sleep(0.1)


    # Due to race-condition described above, the following way to wait for all publish is safer
    msg_info.wait_for_publish()
    

def mqtt_subscribe(topic, callback, qos=1):
    global mqttc
    if mqttc is None:
        print("MQTT client is not initialized. Call mqtt_init() first.")
        return

    # set the on_message callback
    mqttc.on_message = callback

    # subscribe to the specified topic
    result, mid = mqttc.subscribe(topic, qos=qos)
    if result != mqtt.MQTT_ERR_SUCCESS:
        print(f"Failed to subscribe to topic {topic}: {mqttc.error_string(result)}")
    else:
        print(f"Subscribed to topic {topic} with QoS {qos}")


    
def mqtt_done():
    global mqttc
    # disconnect the MQTT client
    if mqttc is not None:
        mqttc.disconnect()
        mqttc.loop_stop()
        mqttc = None
