"""
Test script for RF Bridge parsers.

This script allows you to test your parser modules against a sample RF data string.

Usage:
    python3 test_parser.py <RF_DATA_STRING>

Example:
    python3 test_parser.py A1B201F43C
"""
import os
import sys
import importlib.util
import argparse

# Add the component's root directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers import *

def load_parsers():
    """Loads all parser modules from the 'parsers' directory."""
    parsers_dir = os.path.join(os.path.dirname(__file__), "parsers")
    parser_files = [f for f in os.listdir(parsers_dir) if f.endswith(".py") and not f.startswith("__")]
    
    loaded_parsers = []
    for f in parser_files:
        module_name = f[:-3]
        spec = importlib.util.spec_from_file_location(
            f"parsers.{module_name}", os.path.join(parsers_dir, f)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "parse"):
            loaded_parsers.append((module_name, module.parse))
            print(f"-> Loaded parser: {module_name}")
        else:
            print(f"-> WARNING: {module_name} does not have a 'parse' function.")

    return loaded_parsers

def main():
    """Main function to test the parsers."""
    parser = argparse.ArgumentParser(description="Test RF Bridge parsers.")
    parser.add_argument("data", type=str, help="The RF data string to test (e.g., 'A1B201F43C').")
    args = parser.parse_args()

    print("\nLoading parsers...")
    parsers = load_parsers()

    if not parsers:
        print("\nNo parsers found in the 'parsers' directory.")
        return

    print(f"\nTesting with data: '{args.data}'")
    print("-" * 30)

    found_match = False
    for name, parse_func in parsers:
        try:
            result = parse_func(args.data)
            if result:
                found_match = True
                print(f"SUCCESS: Parser '{name}' matched the data.")
                print(f"  Result: {result}")
            else:
                print(f"INFO: Parser '{name}' did not match.")
        except Exception as e:
            print(f"ERROR: Parser '{name}' raised an exception: {e}")
    
    if not found_match:
        print("\nNo parser was able to handle the provided data.")

if __name__ == "__main__":
    main()
