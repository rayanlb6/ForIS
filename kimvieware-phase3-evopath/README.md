# KIMVIware Phase 3: EvoPath

This service is the third phase in the KIMVIware pipeline. It uses a genetic algorithm called EvoPath to optimize the reduced set of trajectories, balancing coverage, cost, and size.

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
    From the `kimvieware-phase3-evopath` directory, install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

To start the EvoPath service, run the following command from this directory:

```bash
python src/evopath_service.py
```

The service will connect to RabbitMQ and wait for new messages on the `reduction.completed` queue.
