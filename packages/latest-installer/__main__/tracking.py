import os
import sys
import hashlib
import time

# Facebook Conversions API imports
sys.stderr.write("[TRACKING] Module loading started\n")
try:
    from facebook_business.adobjects.serverside.event import Event
    from facebook_business.adobjects.serverside.event_request import EventRequest
    from facebook_business.adobjects.serverside.user_data import UserData
    from facebook_business.adobjects.serverside.custom_data import CustomData
    from facebook_business.adobjects.serverside.action_source import ActionSource
    from facebook_business.api import FacebookAdsApi
    FACEBOOK_SDK_AVAILABLE = True
    sys.stderr.write("[TRACKING] Facebook SDK imported successfully\n")
except ImportError as e:
    FACEBOOK_SDK_AVAILABLE = False
    sys.stderr.write(f"[TRACKING] Facebook SDK not available: {e}\n")


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
            - utm_params: Dict of UTM parameters (utm_source, utm_medium, etc.)
        file_info: Dictionary containing file information:
            - file_name: Name of the file being downloaded
            - file_url: URL of the file
            - source_url: Landing page URL (where the click happened)
    """
    sys.stderr.write("[TRACKING] send_conversion_events called\n")
    print("[DEBUG] send_conversion_events called")
    print(f"[DEBUG] request_data keys: {list(request_data.keys())}")
    print(f"[DEBUG] file_info: {file_info}")

    events_sent = []

    # Try Facebook Conversions API
    if _is_facebook_configured():
        sys.stderr.write("[TRACKING] Facebook is configured, sending event\n")
        print("[DEBUG] Facebook configured, sending event")
        try:
            _send_facebook_event(request_data, file_info)
            sys.stderr.write("[TRACKING] Facebook event sent successfully\n")
            print("[DEBUG] Facebook event sent successfully")
            events_sent.append('facebook')
        except Exception as e:
            sys.stderr.write(f"[TRACKING] Facebook error: {type(e).__name__}: {e}\n")
            print(f"Facebook tracking error: {e}")
    else:
        sys.stderr.write("[TRACKING] Facebook not configured, skipping\n")
        print("[DEBUG] Facebook not configured, skipping")

    return events_sent


def _is_facebook_configured():
    """Check if Facebook credentials are configured."""
    sdk_available = FACEBOOK_SDK_AVAILABLE
    pixel_id = os.environ.get('FB_PIXEL_ID')
    access_token = os.environ.get('FB_ACCESS_TOKEN')

    print(f"[DEBUG] FB config check - SDK: {sdk_available}, Pixel ID: {'Yes' if pixel_id else 'No'}, Token: {'Yes' if access_token else 'No'}")

    is_configured = bool(sdk_available and pixel_id and access_token)
    sys.stderr.write(f"[TRACKING] Facebook configured: {is_configured} (SDK={sdk_available}, Pixel={'Yes' if pixel_id else 'No'}, Token={'Yes' if access_token else 'No'})\n")

    return is_configured


def _send_facebook_event(request_data, file_info):
    """Send conversion event to Facebook Conversions API."""
    sys.stderr.write("[TRACKING] _send_facebook_event called\n")
    print("[DEBUG] _send_facebook_event called")

    if not FACEBOOK_SDK_AVAILABLE:
        raise ImportError("facebook-business SDK not available")

    pixel_id = os.environ.get('FB_PIXEL_ID')
    access_token = os.environ.get('FB_ACCESS_TOKEN')
    event_name = os.environ.get('FB_EVENT_NAME', 'Lead')

    sys.stderr.write(f"[TRACKING] Initializing FB API - pixel={pixel_id[:10]}..., event={event_name}\n")
    print(f"[DEBUG] Initializing Facebook API with pixel_id={pixel_id}, event_name={event_name}")

    # Initialize Facebook API
    FacebookAdsApi.init(access_token=access_token)
    sys.stderr.write("[TRACKING] FB API initialized\n")

    # Build user data
    sys.stderr.write(f"[TRACKING] Building user_data - IP={request_data.get('ip')}\n")
    user_data = UserData(
        client_ip_address=request_data.get('ip'),
        client_user_agent=request_data.get('user_agent'),
        fbp=request_data.get('fbp'),
        fbc=request_data.get('fbc')
    )

    # Add hashed email if provided
    if request_data.get('email'):
        user_data.email = _hash_value(request_data['email'])
        sys.stderr.write("[TRACKING] Added hashed email to user_data\n")

    # Build custom data
    custom_data_kwargs = {
        'content_name': file_info.get('file_name'),
        'value': 1.0,
        'currency': 'USD'
    }

    # Add UTM parameters if present
    utm_params = request_data.get('utm_params', {})
    if utm_params:
        custom_data_kwargs['custom_properties'] = utm_params
        sys.stderr.write(f"[TRACKING] Added UTM params: {list(utm_params.keys())}\n")

    sys.stderr.write(f"[TRACKING] Building custom_data - file={file_info.get('file_name')}\n")
    custom_data = CustomData(**custom_data_kwargs)

    # Create event
    # Use landing page URL (source_url) where click happened, not file URL
    source_url = file_info.get('source_url') or file_info.get('file_url')

    sys.stderr.write(f"[TRACKING] Creating event - source_url={source_url}\n")
    event = Event(
        event_name=event_name,
        event_time=int(time.time()),
        user_data=user_data,
        custom_data=custom_data,
        event_source_url=source_url,
        action_source=ActionSource.WEBSITE
    )

    # Generate event_id for deduplication (in case client-side pixel also fires)
    event_id = _generate_event_id(request_data.get('ip'), file_info.get('file_url'))
    event.event_id = event_id
    sys.stderr.write(f"[TRACKING] Event created with event_id={event_id}\n")

    # Send event
    event_request = EventRequest(
        events=[event],
        pixel_id=pixel_id
    )

    # Add test event code if present
    test_event_code = os.environ.get('FB_TEST_EVENT_CODE')
    if test_event_code:
        event_request.test_event_code = test_event_code
        sys.stderr.write(f"[TRACKING] Using test event code: {test_event_code}\n")

    sys.stderr.write("[TRACKING] Executing Facebook API request...\n")
    print(f"[DEBUG] Executing Facebook event request to API...")
    event_response = event_request.execute()
    sys.stderr.write("[TRACKING] Facebook API request completed successfully\n")
    print(f"[DEBUG] Facebook API responded successfully")
    return event_response


def _hash_value(value):
    """Hash a value using SHA256 for privacy."""
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()


def _generate_event_id(ip, url):
    """Generate deterministic event ID for deduplication."""
    combined = f"{ip}:{url}:{int(time.time() / 60)}"  # Same ID for 1 minute window
    return hashlib.md5(combined.encode()).hexdigest()
