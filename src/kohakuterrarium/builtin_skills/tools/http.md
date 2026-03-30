---
name: http
description: Make HTTP requests to APIs and web services
category: builtin
tags: [network, api, web]
---

# http

Make HTTP requests (GET, POST, PUT, DELETE, PATCH) to APIs and web services.

## WHEN TO USE

- Calling REST APIs to fetch or submit data
- Checking if a web service is up and responding
- Downloading JSON or text content from a URL
- Interacting with webhooks or external integrations
- Testing API endpoints during development

## HOW TO USE

```
tool call: http(
  method: GET
  url: https://api.example.com/resource
)
```

Or with headers and body:

```
tool call: http(
  method: POST
  url: https://api.example.com/resource
  headers: {"Content-Type": "application/json", "Authorization": "Bearer TOKEN"}
{"key": "value", "data": [1, 2, 3]}
)
```

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| method | @@arg | HTTP method: GET, POST, PUT, DELETE, PATCH (default: GET) |
| url | @@arg | Full URL to request (required) |
| headers | @@arg | JSON object of request headers |
| body | content | Request body (e.g. JSON payload) |

## Examples

Simple GET:
```
tool call: http(
  url: https://httpbin.org/get
)
```

POST with JSON body:
```
tool call: http(
  method: POST
  url: https://httpbin.org/post
  headers: {"Content-Type": "application/json"}
{"name": "test", "value": 42}
)
```

PUT with authorization:
```
tool call: http(
  method: PUT
  url: https://api.example.com/items/1
  headers: {"Authorization": "Bearer my-token", "Content-Type": "application/json"}
{"status": "updated"}
)
```

DELETE request:
```
tool call: http(
  method: DELETE
  url: https://api.example.com/items/1
  headers: {"Authorization": "Bearer my-token"}
)
```

## Output Format

```
Status: 200
Content-Type: application/json

{"result": "success", "data": [...]}
```

If the response body exceeds 50KB, it is truncated with a notice.

## LIMITATIONS

- Response body is capped at 50,000 characters
- Request timeout is 30 seconds
- Binary responses (images, files) are not handled well -- use for text/JSON only
- No cookie jar persistence between requests
- Redirects are followed automatically (up to httpx default limit)

## TIPS

- Always include `Content-Type` header for POST/PUT requests with a body
- For JSON APIs, set `  headers: {"Content-Type": "application/json"}`
- Use GET when you only need to read data; use POST/PUT for mutations
- Check the status code in the output to confirm success (2xx) vs error (4xx/5xx)
- For large responses, consider whether you actually need the full body or just the status
