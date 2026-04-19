# KIMVIware Phase 0: Validator

This service is the first phase in the KIMVIware pipeline. It validates the submitted SUT (System Under Test) archive, extracts it, and detects the programming language.

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
    From the `kimvieware-phase0-validator` directory, install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

To start the validator service, run the following command from this directory:

```bash
python src/validator_service.py
```

The service will connect to RabbitMQ and wait for new submission messages on the `submission.new` queue.

## Local Validation (without RabbitMQ)

You can also run the validation logic locally on a file using the `validate_sut.py` script. This is useful for testing or debugging.

```bash
python validate_sut.py /path/to/your/sut.zip
```
