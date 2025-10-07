#!/usr/bin/env python3
"""
Local test script for DigitalOcean Function.
Simulates function invocation to debug issues locally.
"""

import sys
import os
from pathlib import Path

# Load environment variables from .env if available
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded environment from {env_path}")
    else:
        print(f"⚠ No .env file found at {env_path}")
except ImportError:
    print("⚠ python-dotenv not installed, skipping .env loading")
    print("  Install with: pip install python-dotenv")

# Add function directory to Python path
function_dir = Path(__file__).parent / 'packages' / 'latest-installer' / '__main__'
sys.path.insert(0, str(function_dir))

print(f"✓ Added to path: {function_dir}\n")

# Import the function
# Note: Can't use "from __main__ import main" because this script is __main__
# Instead, we import the module by its file path
print("Importing function...")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("function_main", function_dir / '__main__.py')
    function_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(function_module)
    main = function_module.main
    print("✓ Successfully imported main()\n")
except Exception as e:
    print(f"✗ Failed to import: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Simulate DigitalOcean Function args
test_args = {
    # Query parameters can be added here
    # 'bucket': 'my-bucket',
    # 'prefix': 'installers/',
    # 'pattern': r'\.dmg$',

    # Enable tracking to test conversion events
    'track': 'all',

    # Optional: Add UTM parameters for tracking test
    'utm_source': 'test',
    'utm_campaign': 'local_test',
    'utm_medium': 'terminal',
    'email': 'test@test.com',

    # Simulate DigitalOcean HTTP headers (required for Facebook matching)
    # In production, DigitalOcean provides these automatically
    'http': {
        'headers': {
            'x-forwarded-for': '127.0.0.1',  # Client IP
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',  # User agent
            'referer': 'https://example.com/landing-page',  # Landing page URL (optional)
        }
    },

    # Optional: Add Facebook cookies for better matching
    # 'fbp': 'fb.1.1234567890.1234567890',
    # 'fbc': 'fb.1.1234567890.AbCdEfGhIjKlMnOpQrStUvWxYz',
}

print("=" * 60)
print("Testing function with args:")
print(test_args)
print("=" * 60)
print()

# Call the function
try:
    result = main(test_args)
    print("\n" + "=" * 60)
    print("SUCCESS - Function returned:")
    print(result)
    print("=" * 60)
except Exception as e:
    print("\n" + "=" * 60)
    print(f"ERROR - Function raised exception:")
    print(f"{type(e).__name__}: {e}")
    print("=" * 60)
    import traceback
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)
