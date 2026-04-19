# KIMVIware Phase 4: Executor

This service is the final phase in the KIMVIware pipeline. It generates and executes tests based on the optimized set of trajectories and performs mutation testing to assess the quality of the generated tests.

## Prerequisites

*   Python 3.8+
*   The core infrastructure is running (see `kimvieware-infrastructure`), especially RabbitMQ.
*   The `kimvieware-shared` library is installed.
*   The System Under Test (SUT) must be running for the test execution to work.

## Setup

1.  **Install the shared library**:
    If you haven't already, navigate to the `kimvieware-shared` directory and run:

    ```bash
    pip install -e .
    ```

2.  **Install dependencies**:
    From the `kimvieware-phase4-executor` directory, install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

To start the executor service, run the following command from this directory:

```bash
python src/executor_service.py
```

The service will connect to RabbitMQ and wait for new messages on the `optimization.completed` queue.
