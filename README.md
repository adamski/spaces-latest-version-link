# spaces-latest-version

DigitalOcean Function that redirects to the latest installer version in a DigitalOcean Spaces bucket.

## Deployment

```bash
doctl serverless deploy .
```

## Configuration

Set environment variables in the DigitalOcean Functions dashboard (or locally in `.env`):

```bash
SPACES_KEY=your_spaces_access_key
SPACES_SECRET=your_spaces_secret_key
SPACES_REGION=nyc3
SPACES_BUCKET=your-bucket-name      # Optional: can be passed as query param
SPACES_PREFIX=installers/            # Optional: folder prefix
FILE_PATTERN=.*\.(exe|dmg|deb|rpm)$  # Optional: regex to filter files
```

## Get Function URL

```bash
doctl sls fn get latest-installer/__main__ --url
```

This returns a URL like:
```
https://faas-lon1-917a94a7.doserverless.co/api/v1/web/fn-xxx/latest-installer/__main__
```

## Usage

Add the function URL as a download link on your webpage:

```html
<a href="https://faas-lon1-917a94a7.doserverless.co/api/v1/web/fn-xxx/latest-installer/__main__">
  Download Latest Version
</a>
```

When clicked, the function redirects (HTTP 302) to the latest installer file in your Spaces bucket.

## Query Parameters

Override defaults with query parameters:

- `?bucket=my-bucket` - Specify bucket name
- `?prefix=installers/windows/` - Search in specific folder
- `?pattern=\.exe$` - Filter files by regex pattern

Example:
```
https://your-function-url?prefix=installers/mac/&pattern=\.dmg$
```

## How It Works

1. Lists objects in the specified Spaces bucket/folder
2. Filters files by pattern (if provided)
3. Finds latest version using:
   - Semantic versioning (e.g., `v1.2.3`) if detected in filename
   - Falls back to last modified timestamp
4. Returns HTTP 302 redirect to the file URL
