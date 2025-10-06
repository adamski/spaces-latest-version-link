import os
import re
import sys
import boto3
from packaging import version

# Write to stderr to ensure visibility even if stdout is not captured
sys.stderr.write("[EARLY-DEBUG] Module loading started\n")

try:
    from tracking import send_conversion_events
    sys.stderr.write("[EARLY-DEBUG] Successfully imported tracking module\n")
except Exception as e:
    sys.stderr.write(f"[EARLY-DEBUG] CRITICAL: Failed to import tracking: {type(e).__name__}: {e}\n")
    # Provide fallback to prevent function from crashing
    def send_conversion_events(request_data, file_info):
        sys.stderr.write("[ERROR] Tracking not available due to import failure\n")
        return []


def main(args):
    """
    DigitalOcean Function that redirects to the latest installer in Spaces.

    Query parameters:
    - bucket: Spaces bucket name (optional, defaults to env var)
    - prefix: Folder prefix to search in (optional)
    - pattern: Regex pattern to match files (optional, defaults to all files)
    - track: Enable conversion tracking (e.g., 'all')
    """
    # Use both stderr and stdout to maximize visibility
    sys.stderr.write(f"[EARLY-DEBUG] main() called with {len(args)} args\n")
    print(f"[DEBUG] Function called with args keys: {list(args.keys())}")

    # Get configuration from args or environment
    bucket = args.get('bucket', os.environ.get('SPACES_BUCKET'))
    prefix = args.get('prefix', os.environ.get('SPACES_PREFIX', ''))
    pattern = args.get('pattern', os.environ.get('FILE_PATTERN', r'.*'))
    track_enabled = args.get('track')

    print(f"[DEBUG] Config - bucket={bucket}, prefix={prefix}, pattern={pattern}, track={track_enabled}")
    print(f"[DEBUG] Credentials present - SPACES_KEY={'Yes' if os.environ.get('SPACES_KEY') else 'No'}, SPACES_SECRET={'Yes' if os.environ.get('SPACES_SECRET') else 'No'}")

    if not bucket:
        return {
            'statusCode': 400,
            'body': {'error': 'bucket parameter or SPACES_BUCKET environment variable required'}
        }

    # Initialize S3 client for DigitalOcean Spaces
    region = os.environ.get('SPACES_REGION', 'nyc3')
    print(f"[DEBUG] Initializing S3 client for region={region}")
    s3_client = boto3.client(
        's3',
        region_name=region,
        endpoint_url=f'https://{region}.digitaloceanspaces.com',
        aws_access_key_id=os.environ.get('SPACES_KEY'),
        aws_secret_access_key=os.environ.get('SPACES_SECRET')
    )

    try:
        # List objects in bucket
        sys.stderr.write(f"[EARLY-DEBUG] About to call S3 list_objects_v2\n")
        print(f"[DEBUG] Calling S3 list_objects_v2(Bucket={bucket}, Prefix={prefix})")
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        sys.stderr.write(f"[EARLY-DEBUG] S3 call completed\n")
        print(f"[DEBUG] S3 call succeeded, response keys: {list(response.keys())}")

        if 'Contents' not in response or len(response['Contents']) == 0:
            return {
                'statusCode': 404,
                'body': {'error': 'No files found in specified location'}
            }

        # Filter files by pattern
        file_pattern = re.compile(pattern)
        matching_files = [
            obj for obj in response['Contents']
            if file_pattern.search(obj['Key'])
        ]
        print(f"[DEBUG] Found {len(matching_files)} files matching pattern")

        if not matching_files:
            return {
                'statusCode': 404,
                'body': {'error': f'No files matching pattern: {pattern}'}
            }

        # Find latest version
        latest = find_latest_version(matching_files)
        print(f"[DEBUG] Latest file: {latest['Key']}")

        # Build URL
        file_url = f"https://{bucket}.{region}.digitaloceanspaces.com/{latest['Key']}"

        # Send conversion tracking if enabled
        if track_enabled:
            print(f"[DEBUG] Tracking enabled, calling send_conversion_events")
            try:
                request_data = _extract_request_data(args)
                file_info = {
                    'file_name': latest['Key'],
                    'file_url': file_url,
                    'source_url': request_data.get('referrer', '')  # Landing page URL
                }
                send_conversion_events(request_data, file_info)
                print(f"[DEBUG] Tracking completed successfully")
            except Exception as e:
                # Don't break redirect if tracking fails
                print(f"Tracking error: {e}")

        # Return redirect
        print(f"[DEBUG] Returning 302 redirect to: {file_url}")
        return {
            'statusCode': 302,
            'headers': {
                'Location': file_url
            }
        }

    except Exception as e:
        sys.stderr.write(f"[EARLY-DEBUG] EXCEPTION: {type(e).__name__}: {str(e)}\n")
        print(f"[DEBUG] Exception caught: {type(e).__name__}: {str(e)}")
        return {
            'statusCode': 500,
            'body': {'error': str(e)}
        }


def find_latest_version(files):
    """
    Find the latest version from a list of S3 objects.
    Tries semantic versioning first, falls back to last modified timestamp.
    """
    # Try to extract semantic versions from filenames
    version_pattern = re.compile(r'v?(\d+\.\d+\.\d+(?:\.\d+)?)')

    versioned_files = []
    for file in files:
        match = version_pattern.search(file['Key'])
        if match:
            try:
                ver = version.parse(match.group(1))
                versioned_files.append((ver, file))
            except:
                pass

    # If we found versioned files, return the one with highest version
    if versioned_files:
        versioned_files.sort(key=lambda x: x[0], reverse=True)
        return versioned_files[0][1]

    # Fall back to last modified timestamp
    files.sort(key=lambda x: x['LastModified'], reverse=True)
    return files[0]


def _extract_request_data(args):
    """
    Extract request data for conversion tracking.
    DigitalOcean Functions provide request info in the 'http' key.
    """
    # Use modern API (http.headers) with fallback to deprecated __ow_headers
    http_data = args.get('http', {})
    headers = http_data.get('headers', args.get('__ow_headers', {}))

    # Extract UTM parameters from query string
    utm_params = {
        'utm_source': args.get('utm_source'),
        'utm_medium': args.get('utm_medium'),
        'utm_campaign': args.get('utm_campaign'),
        'utm_term': args.get('utm_term'),
        'utm_content': args.get('utm_content'),
    }
    # Remove None values
    utm_params = {k: v for k, v in utm_params.items() if v is not None}

    return {
        'ip': headers.get('x-forwarded-for', '').split(',')[0].strip(),
        'user_agent': headers.get('user-agent', ''),
        'referrer': headers.get('referer', ''),
        'fbp': args.get('fbp'),  # Facebook browser ID from query param or cookie
        'fbc': args.get('fbc'),  # Facebook click ID from query param or cookie
        'fbclid': args.get('fbclid'),  # Facebook click ID from URL
        'utm_params': utm_params  # UTM tracking parameters
    }
