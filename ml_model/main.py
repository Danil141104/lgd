import pika
import json
import os
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
import pickle


HOST = os.environ.get("RABBITMQ_HOST", "localhost")
USERNAME = os.environ.get("RABBITMQ_DEFAULT_USER", "user")
PASSWORD = os.environ.get("RABBITMQ_DEFAULT_PASS", "password")

credentials = pika.PlainCredentials(USERNAME, PASSWORD)
connection = pika.BlockingConnection(
    pika.ConnectionParameters(host=HOST, port=5672, credentials=credentials)
)

channel = connection.channel()

channel.queue_declare(queue="rpc_queue")

def work(params):
    model_input = list(params.values())
    print(model_input)
    predicted = model.predict([model_input])[0]
    print(f"Working on {params}")
    return {"lgd_predicted": max(0, min(1, predicted))}

def on_request(ch, method, props, body):
    params = json.loads(body)
    print(f"Got {params}")

    response = work(params)

    ch.basic_publish(
        exchange="",
        routing_key=props.reply_to,
        properties=pika.BasicProperties(correlation_id=props.correlation_id),
        body=json.dumps(response),
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)


with open('model.pkl', 'rb') as file:
    model = pickle.load(file)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue="rpc_queue", on_message_callback=on_request)

print(" [x] Awaiting RPC requests")
channel.start_consuming()

