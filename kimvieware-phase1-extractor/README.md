# KIMVIware Phase 1: Extractor

This service is responsible for extracting symbolic execution paths from Systems Under Test (SUTs) for various programming languages.

## Prerequisites

*   Python 3.8+
*   The core infrastructure is running (see `kimvieware-infrastructure`), especially RabbitMQ.
*   The `kimvieware-shared` library is installed.
*   For C/C++ extraction, `libclang` must be installed.

## Setup

1.  **Install the shared library**:
    If you haven't already, navigate to the `kimvieware-shared` directory and run:

    ```bash
    pip install -e .
    ```

2.  **Install dependencies**:
    From the `kimvieware-phase1-extractor` directory, install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```

3.  **libclang Setup (for C/C++ Extraction)**:
    The C/C++ extractor (`src/extractors/c_extractor.py`) relies on `libclang` for parsing C/C++ code. `libclang` is part of the LLVM project.

    **Important**: You need to have LLVM/Clang installed on your system. On Ubuntu/Debian, you can install it via:
    ```bash
    sudo apt update
    sudo apt install clang-18 llvm-18-dev libclang-18-dev
    ```

    The extractor will attempt to find `libclang.so` in common locations. If it fails, you might need to set the `CLANG_LIBRARY_PATH` environment variable to the directory containing your `libclang.so` file.
    Example:
    ```bash
    export CLANG_LIBRARY_PATH=/usr/lib/llvm-18/lib/
    ```

 4. **acorn setup **:
    mkdir -p ~/.npm-global
    npm config set prefix '~/.npm-global'
    echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
    source ~/.bashrc

    # Puis
    npm install -g acorn   

## Environment Variables

*   `EXTRACTOR_MAX_PATHS`: Maximum number of paths to extract per job (default: 1000). Set this to control resource usage.

## Usage

To start the extractor service, run the following command from this directory:

```bash
python src/extractor_service.py
```

This service will listen for messages on the `validation.completed` RabbitMQ queue.
