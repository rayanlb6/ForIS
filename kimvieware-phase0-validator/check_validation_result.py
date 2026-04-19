#!/usr/bin/env python3
"""
Check validation result
"""
import pika
import json

credentials = pika.PlainCredentials('admin', 'kimvie2025')
connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost', credentials=credentials)
)
channel = connection.channel()
channel.queue_declare(queue='validation.completed', durable=True)

method, properties, body = channel.basic_get(queue='validation.completed', auto_ack=True)

if method:
    result = json.loads(body)
    print("✅ Validation result:")
    print(json.dumps(result, indent=2))
else:
    print("❌ No result in queue")

connection.close()
