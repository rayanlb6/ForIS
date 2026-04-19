"""
Phase 1 Worker - Path Extraction
Multi-language support: Python, C/C++, Java
"""
import pika
import json
import logging
from pathlib import Path
from datetime import datetime

# Import JobStatus
from kimvieware_shared import MicroserviceBase, JobStatus, Trajectory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - Phase1 - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# RabbitMQ Configuration
RABBITMQ_HOST = "localhost"
RABBITMQ_USER = "admin"
RABBITMQ_PASS = "kimvie2025"


def get_rabbitmq_connection():
    """Create RabbitMQ connection"""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    return pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)
    )


def send_to_queue(queue_name: str, message: dict):
    """Send message to queue"""
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    
    channel.basic_publish(
        exchange='',
        routing_key=queue_name,
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    
    connection.close()
    logger.info(f"📤 Sent to {queue_name}")


def process_job(message: dict):
    """Process extraction job with multi-language support"""
    
    job_id = message['job_id']
    sut_path = Path(message['sut_path'])
    sut_info = message.get('sut_info', {})
    language = sut_info.get('language', 'unknown')
    
    logger.info(f"📦 Processing job {job_id[:8]}... (Language: {language})")
    
    try:
        # Choose extractor based on language
        if language == 'python':
            from extractors.python_extractor import PythonExtractor
            extractor = PythonExtractor(max_paths=100)
            logger.info("Using Python AST extractor")
        
        elif language in ['c', 'cpp']:
            from extractors.c_extractor import CExtractor
            extractor = CExtractor(max_paths=100)
            logger.info("Using C/C++ Clang extractor")
        
        elif language == 'java':
            from extractors.java_extractor import JavaExtractor
            extractor = JavaExtractor(max_paths=100)
            logger.info("Using Java javalang extractor")
        
        else:
            logger.error(f"Unsupported language: {language}")
            raise ValueError(f"Unsupported language: {language}")
        
        # Extract trajectories
        logger.info(f"Extracting paths from {sut_path}...")
        trajectories = extractor.extract_paths(sut_path)
        
        logger.info(f"✅ Extracted {len(trajectories)} trajectories")
        
        # Prepare result
        result = {
            'job_id': job_id,
            'status': JobStatus.EXTRACTED.value, # Added status here
            'sut_info': sut_info,
            'trajectories': [
                {
                    'path_id': t.path_id,
                    'basic_blocks': t.basic_blocks,
                    'path_condition': t.path_condition,
                    'branches_covered': list(t.branches_covered),
                    'constraints': t.constraints,
                    'cost': t.cost,
                    'is_feasible': t.is_feasible
                }
                for t in trajectories
            ],
            'metadata': {
                'language': language,
                'extractor': 'python' if language == 'python' else ('clang' if language in ['c', 'cpp'] else 'javalang'),
                'trajectories_count': len(trajectories),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        }
        
        # Send to Phase 2
        send_to_queue('extraction.completed', result)
        logger.info(f"✅ Job {job_id[:8]} completed - sent to Phase 2")
        
    except Exception as e:
        logger.error(f"❌ Error processing job {job_id[:8]}: {e}")
        raise


def callback(ch, method, properties, body):
    """RabbitMQ callback"""
    try:
        message = json.loads(body)
        logger.info(f"📥 Received job: {message['job_id'][:8]}")
        
        process_job(message)
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"❌ Error in callback: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main():
    """Main worker loop"""
    logger.info("=" * 60)
    logger.info("🚀 Phase 1 Worker - Path Extraction")
    logger.info("   Multi-Language: Python, C, C++, Java")
    logger.info("=" * 60)
    
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    
    # Declare queues
    channel.queue_declare(queue='validation.completed', durable=True)
    channel.queue_declare(queue='extraction.completed', durable=True)
    
    # Set QoS
    channel.basic_qos(prefetch_count=1)
    
    # Start consuming
    channel.basic_consume(
        queue='validation.completed',
        on_message_callback=callback
    )
    
    logger.info("✅ Worker ready - waiting for jobs...")
    logger.info("   Listening on: validation.completed")
    logger.info("   Output to: extraction.completed")
    logger.info("")
    
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("\n⏸️  Worker stopped by user")
        channel.stop_consuming()
    
    connection.close()


if __name__ == "__main__":
    main()