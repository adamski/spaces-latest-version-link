import os
import re
import boto3
import hashlib
import time
from packaging import version

# Facebook Conversions API imports (only loaded when tracking is used)
try:
    from facebook_business.adobjects.serverside.event import Event
    from facebook_business.adobjects.serverside.event_request import EventRequest
    from facebook_business.adobjects.serverside.user_data import UserData
    from facebook_business.adobjects.serverside.custom_data import CustomData
    from facebook_business.api import FacebookAdsApi
    FACEBOOK_SDK_AVAILABLE = True
except ImportError:
    FACEBOOK_SDK_AVAILABLE = False


def main(args):
    """
    DigitalOcean Function that redirects to the latest installer in Spaces.

    Query parameters:
    - bucket: Spaces bucket name (optional, defaults to env var)
    - prefix: Folder prefix to search in (optional)
    - pattern: Regex pattern to match files (optional, defaults to all files)
    - track: Enable conversion tracking (e.g., 'all')
    """
    # Get configuration from args or environment
    bucket = args.get('bucket', os.environ.get('SPACES_BUCKET'))
    prefix = args.get('prefix', os.environ.get('SPACES_PREFIX', ''))
    pattern = args.get('pattern', os.environ.get('FILE_PATTERN', r'.*'))
    track_enabled = args.get('track')

    if not bucket:
        return {
            'statusCode': 400,
            'body': {'error': 'bucket parameter or SPACES_BUCKET environment variable required'}
        }

    # Initialize S3 client for DigitalOcean Spaces
    region = os.environ.get('SPACES_REGION', 'nyc3')
    s3_client = boto3.client(
        's3',
        region_name=region,
        endpoint_url=f'https://{region}.digitaloceanspaces.com',
        aws_access_key_id=os.environ.get('SPACES_KEY'),
        aws_secret_access_key=os.environ.get('SPACES_SECRET')
    )

    try:
        # List objects in bucket
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

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

        if not matching_files:
            return {
                'statusCode': 404,
                'body': {'error': f'No files matching pattern: {pattern}'}
            }

        # Find latest version
        latest = find_latest_version(matching_files)

        # Build URL
        file_url = f"https://{bucket}.{region}.digitaloceanspaces.com/{latest['Key']}"

        # Send conversion tracking if enabled
        if track_enabled:
            try:
                request_data = _extract_request_data(args)
                file_info = {
                    'file_name': latest['Key'],
                    'file_url': file_url,
                    'source_url': request_data.get('referrer', '')  # Landing page URL
                }
                send_conversion_events(request_data, file_info)
            except Exception as e:
                # Don't break redirect if tracking fails
                print(f"Tracking error: {e}")

        # Return redirect
        return {
            'statusCode': 302,
            'headers': {
                'Location': file_url
            }
        }

    except Exception as e:
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

    return {
        'ip': headers.get('x-forwarded-for', '').split(',')[0].strip(),
        'user_agent': headers.get('user-agent', ''),
        'referrer': headers.get('referer', ''),
        'fbp': args.get('fbp'),  # Facebook browser ID from query param or cookie
        'fbc': args.get('fbc'),  # Facebook click ID from query param or cookie
        'fbclid': args.get('fbclid')  # Facebook click ID from URL
    }


# ============================================================================
# Conversion Tracking Functions (previously in tracking.py)
# ============================================================================

def send_conversion_events(request_data, file_info):
    """
    Send conversion events to all configured platforms.

    Args:
        request_data: Dictionary containing request information:
            - ip: Client IP address
            - user_agent: User agent string
            - referrer: HTTP referrer (landing page URL)
            - fbp: Facebook browser ID cookie (_fbp)
            - fbc: Facebook click ID cookie (_fbc)
            - fbclid: Facebook click ID from URL
        file_info: Dictionary containing file information:
            - file_name: Name of the file being downloaded
            - file_url: URL of the file
            - source_url: Landing page URL (where the click happened)
    """
    events_sent = []

    # Try Facebook Conversions API
    if _is_facebook_configured():
        try:
            _send_facebook_event(request_data, file_info)
            events_sent.append('facebook')
        except Exception as e:
            print(f"Facebook tracking error: {e}")

    return events_sent


def _is_facebook_configured():
    """Check if Facebook credentials are configured."""
    return bool(
        FACEBOOK_SDK_AVAILABLE and
        os.environ.get('FB_PIXEL_ID') and
        os.environ.get('FB_ACCESS_TOKEN')
    )


def _send_facebook_event(request_data, file_info):
    """Send conversion event to Facebook Conversions API."""
    if not FACEBOOK_SDK_AVAILABLE:
        raise ImportError("facebook-business SDK not available")

    pixel_id = os.environ.get('FB_PIXEL_ID')
    access_token = os.environ.get('FB_ACCESS_TOKEN')
    event_name = os.environ.get('FB_EVENT_NAME', 'Lead')

    # Initialize Facebook API
    FacebookAdsApi.init(access_token=access_token)

    # Build user data
    user_data = UserData(
        client_ip_address=request_data.get('ip'),
        client_user_agent=request_data.get('user_agent'),
        fbp=request_data.get('fbp'),
        fbc=request_data.get('fbc')
    )

    # Add hashed email if provided
    if request_data.get('email'):
        user_data.email = _hash_value(request_data['email'])

    # Build custom data
    custom_data = CustomData(
        content_name=file_info.get('file_name'),
        value=1.0,
        currency='USD'
    )

    # Create event
    # Use landing page URL (source_url) where click happened, not file URL
    source_url = file_info.get('source_url') or file_info.get('file_url')
    event = Event(
        event_name=event_name,
        event_time=int(time.time()),
        user_data=user_data,
        custom_data=custom_data,
        event_source_url=source_url,
        action_source='website'
    )

    # Generate event_id for deduplication (in case client-side pixel also fires)
    event_id = _generate_event_id(request_data.get('ip'), file_info.get('file_url'))
    event.event_id = event_id

    # Send event
    event_request = EventRequest(
        events=[event],
        pixel_id=pixel_id
    )

    # Add test event code if present
    test_event_code = os.environ.get('FB_TEST_EVENT_CODE')
    if test_event_code:
        event_request.test_event_code = test_event_code

    event_response = event_request.execute()
    return event_response


def _hash_value(value):
    """Hash a value using SHA256 for privacy."""
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()


def _generate_event_id(ip, url):
    """Generate deterministic event ID for deduplication."""
    combined = f"{ip}:{url}:{int(time.time() / 60)}"  # Same ID for 1 minute window
    return hashlib.md5(combined.encode()).hexdigest()