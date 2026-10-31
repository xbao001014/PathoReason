"""Use the selected GPU for a new command, preserving engine training gates."""
import argparse
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.compute_exec import execution_environment
from pathoreason.settings import settings

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--turn', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('a command is required after --')
    environment = execution_environment(settings(), args.turn)
    os.execvpe(command[0], command, environment)

if __name__ == '__main__':
    main()
