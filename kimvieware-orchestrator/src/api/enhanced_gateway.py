from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Import shared utilities for RabbitMQ
from kimvieware_shared.utils.rabbitmq import create_connection, declare_queue, publish_message
from kimvieware_shared.utils.logging import setup_logger
from kimvieware_shared.storage.job_storage import JobStorage

# Root of the orchestrator (contains templates/ and static/)
BASE_DIR = Path(__file__).resolve().parents[2]

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

import threading

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown"""
    # Startup
    # Start RabbitMQ consumers in a background thread so they don't block FastAPI startup
    thread = threading.Thread(target=_start_message_consumers, daemon=True)
    thread.start()
    yield
    # Shutdown - nothing to do

app = FastAPI(title="KIMVIEware Orchestrator", lifespan=lifespan)

# In-memory store (simple demo implementation) - REMOVED
# jobs: Dict[str, Dict] = {}

services_status = {
    "validator": {"name": "Phase 0 - Validator", "status": "offline"},
    "extractor": {"name": "Phase 1 - Extractor", "status": "offline"},
    "sgats": {"name": "Phase 2 - SGATS", "status": "offline"},
    "evopath": {"name": "Phase 3 - EvoPath", "status": "offline"},
    "executor": {"name": "Phase 4 - Executor", "status": "offline"},
}

# Initialize JobStorage for MongoDB access
job_storage = JobStorage()

# RabbitMQ connection for publishing jobs
rabbitmq_connection = None
rabbitmq_channel = None
logger = setup_logger("Orchestrator")

def _get_rabbitmq_channel():
    """Get or create RabbitMQ channel"""
    global rabbitmq_connection, rabbitmq_channel
    if rabbitmq_connection is None or rabbitmq_connection.is_closed:
        rabbitmq_connection = create_connection(logger=logger)
        rabbitmq_channel = rabbitmq_connection.channel()
        declare_queue(rabbitmq_channel, 'submission.new')
    return rabbitmq_channel

def _start_message_consumers():
    """Start a consumer for phase update events (phase.updates)."""
    import pika
    import json
    from datetime import datetime

    def callback(ch, method, properties, body):
        try:
            message = json.loads(body.decode('utf-8'))
            job_id = message.get('job_id')
            status = message.get('status')

            if not job_id or not status:
                logger.warning("Received invalid phase update message without job_id/status")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            logger.info(f"📥 Phase update for job {job_id}: {status}")

            phase_from_status = {
                'validated': 'phase0',
                'validation_failed': 'phase0',
                'extracted': 'phase1',
                'extraction_failed': 'phase1',
                'reduced': 'phase2',
                'reduction_failed': 'phase2',
                'optimized': 'phase3',
                'optimization_failed': 'phase3',
                'completed': 'phase4',
                'execution_failed': 'phase4',
                'failed': 'phase0'
            }
            phase_key = phase_from_status.get(status, None)
            if phase_key is None:
                logger.warning(f"Unknown status '{status}' in phase update")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Update phase record and main job fields
            phase_data = {**message.get('metadata', {}), 'status': status}

            if status in ['validated', 'validation_failed']:
                phase_data.update({
                    'language': message.get('sut_info', {}).get('language'),
                    'framework': message.get('sut_info', {}).get('framework'),
                    'files_count': message.get('sut_info', {}).get('files_count'),
                    'size_bytes': message.get('sut_info', {}).get('size_bytes'),
                    'entry_point': message.get('sut_info', {}).get('entry_point'),
                    'extracted_path': message.get('extracted_path')
                })

            if status in ['extracted', 'extraction_failed']:
                phase_data.update({
                    'trajectories_count': message.get('trajectories_count'),
                    'trajectories': message.get('trajectories')
                })

            if 'sgats_stats' in message:
                phase_data['sgats_stats'] = message.get('sgats_stats')

            if 'evopath_stats' in message:
                phase_data['evopath_stats'] = message.get('evopath_stats')

            if 'execution_stats' in message:
                phase_data['execution_stats'] = message.get('execution_stats')
            if 'mutation_stats' in message:
                phase_data['mutation_stats'] = message.get('mutation_stats')

            job_storage.update_phase(job_id, phase_key, phase_data)
            
            # Build global job update
            job_update = {
                'job_id': job_id,
                'status': status,
                'error': message.get('error'),
                'phase': message.get('phase'),
                'updated_at': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Promote stats to top level for dashboard and global stats visibility
            if 'mutation_stats' in message:
                job_update['mutation_stats'] = message.get('mutation_stats')
            if 'execution_stats' in message:
                job_update['execution_stats'] = message.get('execution_stats')
            if 'sgats_stats' in message:
                job_update['sgats_stats'] = message.get('sgats_stats')
            if 'evopath_stats' in message:
                job_update['evopath_stats'] = message.get('evopath_stats')
                
            job_storage.save_job(job_update)

            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(f"✅ Updated MongoDB from phase.updates for job {job_id}")

        except Exception as e:
            logger.error(f"❌ Error processing phase update: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    try:
        connection = create_connection(logger=logger)
        channel = connection.channel()
        declare_queue(channel, 'phase.updates')
        channel.basic_consume(queue='phase.updates', on_message_callback=callback)
        logger.info("🚀 Started consumer for phase.updates")
        channel.start_consuming()
    except Exception as e:
        logger.error(f"❌ Failed to start consumer for phase.updates: {e}")



def _make_job(job_id: str, filename: str, content_len: int) -> Dict:
    return {
        "job_id": job_id,
        "filename": filename,
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
        "file_size": content_len,
        "status": "SUBMITTED",
        "phases": {
            "phase0": {"status": "pending", "progress": 0},
            "phase1": {"status": "pending", "progress": 0},
            "phase2": {"status": "pending", "progress": 0},
            "phase3": {"status": "pending", "progress": 0},
            "phase4": {"status": "pending", "progress": 0}
        },
        "error": None,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Serve the dashboard UI."""
    return templates.TemplateResponse("dashboard_pro.html", {"request": request})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/submit")
async def submit_sut(file: UploadFile = File(...)):
    """Submit a SUT file and publish it to the pipeline"""
    try:
        # Generate job ID based on existing jobs count
        all_jobs = job_storage.get_all_jobs(limit=1000)  # Get more jobs to avoid conflicts
        job_id = f"job_{len(all_jobs) + 1:04d}"

        # Read file content
        content = await file.read()

        # Save file to disk for processing
        upload_dir = BASE_DIR / "uploads"
        upload_dir.mkdir(exist_ok=True)
        file_path = upload_dir / f"{job_id}_{file.filename}"
        with open(file_path, "wb") as f:
            f.write(content)

        # Create job record
        job = _make_job(job_id, file.filename, len(content))

        # Save to MongoDB
        job_storage.save_job(job)

        # Prepare message for RabbitMQ (what validator expects)
        message = {
            "job_id": job_id,
            "sut_path": str(file_path),  # File path on disk
            "filename": file.filename,
            "file_size": len(content),
            "submitted_at": job["uploaded_at"],
            "status": "submitted"
        }

        # Publish to RabbitMQ
        channel = _get_rabbitmq_channel()
        publish_message(channel, 'submission.new', message)
        logger.info(f"📤 Published job {job_id} to 'submission.new' queue")

        return {"job_id": job_id}

    except Exception as e:
        logger.error(f"❌ Error submitting job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {str(e)}")


@app.get("/api/jobs")
def list_jobs():
    """Get all jobs from MongoDB"""
    try:
        all_jobs = job_storage.get_all_jobs(limit=50)
        return {"total": len(all_jobs), "jobs": all_jobs}
    except Exception as e:
        logger.error(f"❌ Error getting jobs: {e}")
        return {"total": 0, "jobs": []}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """Get specific job from MongoDB"""
    try:
        job = job_storage.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get job: {str(e)}")


@app.get("/api/services")
def get_services():
    # Check actual service status by trying to connect to RabbitMQ queues or ports
    import socket
    
    service_checks = {
        "validator": {"port": 5672, "queue": "submission.new"},  # RabbitMQ port
        "extractor": {"port": 5672, "queue": "validation.completed"},
        "sgats": {"port": 5672, "queue": "extraction.completed"},
        "evopath": {"port": 5672, "queue": "reduction.completed"},
        "executor": {"port": 5672, "queue": "optimization.completed"},
    }
    
    for service_key, check in service_checks.items():
        try:
            # Check if RabbitMQ is accessible (services communicate via RabbitMQ)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', check["port"]))
            sock.close()
            
            if result == 0:
                services_status[service_key]["status"] = "online"
            else:
                services_status[service_key]["status"] = "offline"
        except:
            services_status[service_key]["status"] = "unknown"
    
    return services_status


@app.get("/api/services/{service_key}/health")
def check_service_health(service_key: str):
    """Check health of a specific service"""
    if service_key not in services_status:
        raise HTTPException(status_code=404, detail=f"Service {service_key} not found")
    
    # For now, just return basic health info
    # In a real implementation, this would check actual service health
    return {
        "service": service_key,
        "status": services_status[service_key]["status"],
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@app.get("/api/services/{service_key}/logs")
def get_service_logs(service_key: str):
    """Get logs for a specific service"""
    if service_key not in services_status:
        raise HTTPException(status_code=404, detail=f"Service {service_key} not found")
    
    # For now, return placeholder logs
    # In a real implementation, this would fetch actual logs
    return f"Logs for service {service_key} - Status: {services_status[service_key]['status']}\n[TIMESTAMP] Service started\n[TIMESTAMP] Processing jobs..."


@app.post("/api/services/{service_key}/restart")
def restart_service(service_key: str):
    """Restart a specific service"""
    if service_key not in services_status:
        raise HTTPException(status_code=404, detail=f"Service {service_key} not found")
    
    # For now, just update status temporarily
    # In a real implementation, this would actually restart the service
    services_status[service_key]["status"] = "restarting"
    
    # Simulate restart
    import threading
    def simulate_restart():
        import time
        time.sleep(2)
        services_status[service_key]["status"] = "online"
    
    thread = threading.Thread(target=simulate_restart)
    thread.daemon = True
    thread.start()
    
    return {"message": f"Service {service_key} restart initiated"}


@app.get("/api/stats")
def get_stats():
    """Get statistics from MongoDB"""
    try:
        all_jobs = job_storage.get_all_jobs(limit=1000)
        total = len(all_jobs)
        
        # Count completed jobs (jobs that have reached certain successful phases)
        completed = sum(1 for j in all_jobs if j.get("status") in [
            "completed", "validated", "extracted", "reduced", "optimized"
        ])
        
        # Calculate average mutation score from completed jobs
        mutation_scores = []
        for job in all_jobs:
            if job.get("status") == "completed" and job.get("mutation_stats"):
                score = job["mutation_stats"].get("mutation_score")
                if score is not None:
                    mutation_scores.append(score)
        
        avg_mutation_score = None
        if mutation_scores:
            avg_mutation_score = sum(mutation_scores) / len(mutation_scores)
        
        # Calculate average reduction from SGATS and EvoPath
        reductions = []
        for job in all_jobs:
            if job.get("status") == "completed":
                # SGATS reduction
                sgats_stats = job.get("sgats_stats")
                if sgats_stats and sgats_stats.get("reduction_rate") is not None:
                    reductions.append(sgats_stats["reduction_rate"] * 100)
                # EvoPath size reduction
                evopath_stats = job.get("evopath_stats")
                if evopath_stats and evopath_stats.get("size_reduction") is not None:
                    reductions.append(evopath_stats["size_reduction"] * 100)
        
        avg_reduction = None
        if reductions:
            avg_reduction = sum(reductions) / len(reductions)
        
        return {
            "total_jobs": total,
            "completed": completed,
            "success_rate": 100.0 if total == 0 else (completed / total) * 100,
            "mutation_score": avg_mutation_score,
            "avg_reduction": avg_reduction,
        }
    except Exception as e:
        logger.error(f"❌ Error getting stats: {e}")
        return {
            "total_jobs": 0,
            "completed": 0,
            "success_rate": 0.0,
            "mutation_score": None,
            "avg_reduction": None,
        }
