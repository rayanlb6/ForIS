# KIMVIware Phase 2: SGATS

This service is the second phase in the KIMVIware pipeline. It uses the SGATS (Similarity-Guided Abstract Trajectory Selection) algorithm to reduce the set of symbolic execution paths (trajectories) to a smaller, more manageable set.

## Prerequisites

*   Python 3.8+
*   The core infrastructure is running (see `kimvieware-infrastructure`), especially RabbitMQ.
*   The `kimvieware-shared` library is installed.

## Setup

1.  **Install the shared library**:
    If you haven't already, navigate to the `kimvieware-shared` directory and run:

    ```bash
    pip install -e .
    ```

2.  **Install dependencies**:
    From the `kimvieware-phase2-sgats` directory, install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

To start the SGATS service, run the following command from this directory:

```bash
python src/sgats_service.py
```

The service will connect to RabbitMQ and wait for new messages on the `extraction.completed` queue.
