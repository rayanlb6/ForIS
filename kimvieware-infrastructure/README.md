# KIMVIware Infrastructure

This directory contains the core infrastructure for the KIMVIware project, managed via Docker Compose.

## Services

The `docker-compose.yml` file defines the following services:

*   **RabbitMQ**: Message broker for communication between services.
    *   AMQP port: `5672`
    *   Management UI: `http://localhost:15672`
*   **MongoDB**: Primary database for storing data.
    *   Port: `27017`
*   **MinIO**: S3-compatible object storage for files.
    *   S3 API: `9000`
    *   Web Console: `http://localhost:9001`
*   **Redis**: In-memory data store for caching and session management.
    *   Port: `6379`
*   **kimvieware-monitor**: A custom service for monitoring.
*   **mongodb_exporter**: Prometheus exporter for MongoDB metrics.
    *   Port: `9216`

## Prerequisites

*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/install/)

## Usage

### Start the infrastructure

To start all the services in detached mode, run the following command from this directory:

```bash
docker-compose up -d
```

### Stop the infrastructure

To stop all the running services, use the following command:

```bash
docker-compose down
```

### View logs

To view the logs of all services, you can use:

```bash
docker-compose logs -f
```

To view the logs of a specific service, append the service name:

```bash
docker compose logs -f rabbitmq
docker-compose logs -f rabbitmq
```
