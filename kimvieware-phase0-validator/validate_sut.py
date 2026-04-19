#!/usr/bin/env python3
"""
Local SUT validator runner — validates a given archive and prints JSON result.
"""
import argparse
import json
import sys
from pathlib import Path
import uuid

# Ensure local src package is importable
from src.validator_service import ValidatorService


def main():
    p = argparse.ArgumentParser()
    p.add_argument('sut', type=Path, help='Path to SUT archive (zip/tar)')
    p.add_argument('--job-id', default=str(uuid.uuid4()))
    p.add_argument('--quiet', action='store_true')
    args = p.parse_args()

    service = ValidatorService()
    message = {
        'job_id': args.job_id,
        'sut_path': str(args.sut)
    }

    result = service.process_message(message)

    if not args.quiet:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))


if __name__ == '__main__':
    main()
