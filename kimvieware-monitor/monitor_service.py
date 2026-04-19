"""
KIMVIEware Monitor Service

Listens to all *.completed queues and updates MongoDB with job status.
"""
import os
import pika
import json
import logging
from datetime import datetime

from kimvieware_shared import MicroserviceBase, JobStorage, JobStatus, setup_logger # Import setup_logger

logger = logging.getLogger(__name__)

class MonitorService(MicroserviceBase):
    """Monitors job completion queues and updates central storage"""
    
    def __init__(self):
        # Monitor does not have a single input/output queue like other services
        # It listens to multiple queues and updates the DB directly
        super().__init__(
            service_name="KIMVIEware_Monitor",
            input_queue="monitor.control", # Dummy queue for MicroserviceBase
            output_queue="monitor.log"     # Dummy queue for MicroserviceBase
        )
        
        self.storage = JobStorage()
        self.monitor_queues = [
            'validation.completed',
            'extraction.completed',
            'reduction.completed',
            'optimization.completed',
            'execution.completed'
        ]
        self.channel = None # Will be set in _connect
        
        # Override logger from MicroserviceBase to use its setup
        self.logger = setup_logger(self.service_name)
        
        self.logger.info(f"🚀 {self.service_name} initialized. Monitoring {len(self.monitor_queues)} queues.")
    
    def _connect(self):
        """Connect to RabbitMQ and declare all monitor queues"""
        self.connection = self._create_connection() # Use internal helper
        self.channel = self.connection.channel()
        
        for queue_name in self.monitor_queues:
            self.channel.queue_declare(queue=queue_name, durable=True)
            self.logger.info(f"Declared and listening on queue: {queue_name}")
            
        # Declare dummy queues for MicroserviceBase if not already declared
        self.channel.queue_declare(queue=self.input_queue, durable=True)
        self.channel.queue_declare(queue=self.output_queue, durable=True)
    
    def _create_connection(self):
        """Helper to create RabbitMQ connection (can't use create_connection from shared directly as it requires logger)"""
        # Load RabbitMQ config from environment variables
        rabbitmq_host = os.getenv('RABBITMQ_HOST', 'localhost')
        rabbitmq_user = os.getenv('RABBITMQ_USER', 'admin')
        rabbitmq_pass = os.getenv('RABBITMQ_PASS', 'kimvie2025')
        
        credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_pass)
        return pika.BlockingConnection(
            pika.ConnectionParameters(host=rabbitmq_host, credentials=credentials)
        )

    def process_message(self, message: dict) -> dict:
        """Process a message from a completed queue and update MongoDB"""
        
        job_id = message.get('job_id')
        status = message.get('status')
        phase_name = message.get('phase', 'unknown') # e.g., 'extraction', 'validation'
        
        if not job_id:
            self.logger.error(f"Received message without job_id: {message}")
            return {"status": "failed", "error": "No job_id"}
        
        self.logger.info(f"[{job_id}] Received completion message for phase '{phase_name}' with status '{status}'")
        
        # Update overall job status
        self.storage.save_job({'job_id': job_id, 'status': status, 'updated_at': datetime.now(timezone.utc)})
        
        # Store phase-specific data
        if phase_name != 'unknown':
            # Remove job_id and status from phase_data to avoid redundancy, keep original message content
            phase_data = {k: v for k, v in message.items() if k not in ['job_id', 'status', 'phase']}
            self.storage.update_phase(job_id, phase_name, phase_data)
        
        self.logger.info(f"[{job_id}] MongoDB updated for phase '{phase_name}'")
        
        # Monitor service does not produce messages for the next phase in the pipeline,
        # so return an empty dict or a confirmation.
        return {"job_id": job_id, "status": "processed_by_monitor"}

    def start(self):
        """Start consuming from all monitor queues"""
        self.logger.info(f"🎬 Starting {self.service_name}...")
        self._connect()
        self.channel.basic_qos(prefetch_count=1)
        
        for queue_name in self.monitor_queues:
            self.logger.info(f"✨ Ready! Waiting on '{queue_name}'...")
            self.channel.basic_consume(queue=queue_name, on_message_callback=self._callback_wrapper(queue_name))
            
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.stop()

    def _callback_wrapper(self, queue_name: str):
        """Wrapper for the callback to include queue_name context"""
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body)
                # Add phase name to message for easy identification in process_message
                message['phase'] = queue_name.split('.')[0] # e.g., 'validation' from 'validation.completed'
                
                self.logger.info(f"📥 Received from '{queue_name}': {message.get('job_id', 'N/A')}")
                
                result = self.process_message(message)
                
                # Monitor doesn't publish to a next service queue, so just ack
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except Exception as e:
                self.logger.error(f"❌ Error in monitor callback for queue '{queue_name}': {e}", exc_info=True)
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Do not requeue on error
        return callback


if __name__ == "__main__":
    # Ensure logging is configured before service starts
    logging.basicConfig(level=logging.INFO)
    service = MonitorService()
    service.start()
