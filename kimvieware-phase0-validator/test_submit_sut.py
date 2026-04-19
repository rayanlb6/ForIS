#!/usr/bin/env python3
"""
Submit auth-service.zip to Phase 0 Validator
"""
import pika
import json
import uuid
from pathlib import Path

# SUT path
sut_path = Path.home() / "KIMVIWARE" / "KIMVIEware-System-kimvieware-sut-timetables" / "auth-service.zip"

if not sut_path.exists():
    print(f"❌ File not found: {sut_path}")
    print("Creating ZIP now...")
    import subprocess
    subprocess.run([
        "zip", "-r", str(sut_path),
        str(sut_path.parent / "auth-service"),
        "-x", "*__pycache__/*", "*/.pytest_cache/*"
    ])

# Connect RabbitMQ
credentials = pika.PlainCredentials('admin', 'kimvie2025')
connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost', credentials=credentials)
)
channel = connection.channel()
channel.queue_declare(queue='submission.new', durable=True)

# Create message
message = {
    'job_id': str(uuid.uuid4()),
    'sut_path': str(sut_path),
    'user_id': 'flavie.ndemafo',
    'timestamp': '2026-01-14T16:00:00Z'
}

# Send
channel.basic_publish(
    exchange='',
    routing_key='submission.new',
    body=json.dumps(message),
    properties=pika.BasicProperties(delivery_mode=2)
)

print(f"✅ Submitted: {message['job_id']}")
print(f"   SUT: {sut_path.name}")
print(f"   Size: {sut_path.stat().st_size / 1024:.1f} KB")

connection.close()
