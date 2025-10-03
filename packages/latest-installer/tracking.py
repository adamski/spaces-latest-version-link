import os
import hashlib
import time
from facebook_business.adobjects.serverside.event import Event
from facebook_business.adobjects.serverside.event_request import EventRequest
from facebook_business.adobjects.serverside.user_data import UserData
from facebook_business.adobjects.serverside.custom_data import CustomData
from facebook_business.api import FacebookAdsApi


def send_conversion_events(request_data, file_info):
    """
    Send conversion events to all configured platforms.

    Args:
        request_data: Dictionary containing request information:
            - ip: Client IP address
            - user_agent: User agent string
            - referrer: HTTP referrer
            - fbp: Facebook browser ID cookie (_fbp)
            - fbc: Facebook click ID cookie (_fbc)
            - fbclid: Facebook click ID from URL
        file_info: Dictionary containing file information:
            - file_name: Name of the file being downloaded
            - file_url: URL of the file
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
    return bool(os.environ.get('FB_PIXEL_ID') and os.environ.get('FB_ACCESS_TOKEN'))


def _send_facebook_event(request_data, file_info):
    """Send conversion event to Facebook Conversions API."""
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
    event = Event(
        event_name=event_name,
        event_time=int(time.time()),
        user_data=user_data,
        custom_data=custom_data,
        event_source_url=file_info.get('file_url'),
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
