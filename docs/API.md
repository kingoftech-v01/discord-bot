# API Documentation

Discord Bot Pro provides a REST API for external integrations.

## Overview

- **Base URL**: `http://localhost:8000/api/v1/`
- **Authentication**: API Key or Discord OAuth
- **Format**: JSON
- **Documentation**: Swagger UI at `/api/docs/`

## Authentication

### API Key Authentication

Include the API key in the header:

```http
Authorization: Api-Key YOUR_API_KEY
```

### OAuth Authentication

Use Discord OAuth tokens:

```http
Authorization: Bearer YOUR_OAUTH_TOKEN
```

## Interactive Documentation

- **Swagger UI**: `/api/docs/`
- **ReDoc**: `/api/redoc/`
- **OpenAPI Schema**: `/api/schema/`

## Endpoints

### Guilds

#### List Guilds

```http
GET /api/v1/guilds/
```

Returns guilds where the authenticated user has admin permissions.

**Response:**
```json
{
  "count": 2,
  "results": [
    {
      "id": "123456789",
      "name": "My Server",
      "icon": "abc123",
      "member_count": 150,
      "bot_present": true
    }
  ]
}
```

#### Get Guild

```http
GET /api/v1/guilds/{guild_id}/
```

**Response:**
```json
{
  "id": "123456789",
  "name": "My Server",
  "config": {
    "prefix": "!",
    "leveling_enabled": true,
    "auto_mod_enabled": true
  },
  "stats": {
    "users": 150,
    "warnings": 12,
    "infractions": 5
  }
}
```

#### Update Guild Config

```http
PATCH /api/v1/guilds/{guild_id}/
```

**Request:**
```json
{
  "prefix": "?",
  "leveling_enabled": false
}
```

### Users

#### List Guild Users

```http
GET /api/v1/guilds/{guild_id}/users/
```

**Query Parameters:**
- `page`: Page number
- `page_size`: Results per page (max 100)
- `ordering`: Sort field (`-total_xp`, `level`, etc.)

**Response:**
```json
{
  "count": 150,
  "next": "/api/v1/guilds/123/users/?page=2",
  "results": [
    {
      "user_id": "987654321",
      "username": "Player1",
      "level": 15,
      "total_xp": 5000,
      "balance": 1500,
      "messages_count": 234
    }
  ]
}
```

#### Get User

```http
GET /api/v1/guilds/{guild_id}/users/{user_id}/
```

#### Update User

```http
PATCH /api/v1/guilds/{guild_id}/users/{user_id}/
```

**Request:**
```json
{
  "total_xp": 10000,
  "balance": 5000
}
```

### Moderation

#### List Warnings

```http
GET /api/v1/guilds/{guild_id}/warnings/
```

**Query Parameters:**
- `user_id`: Filter by user
- `moderator_id`: Filter by moderator

#### Create Warning

```http
POST /api/v1/guilds/{guild_id}/warnings/
```

**Request:**
```json
{
  "user_id": "987654321",
  "reason": "Spam"
}
```

#### Delete Warning

```http
DELETE /api/v1/guilds/{guild_id}/warnings/{warning_id}/
```

### Profanity Filter

#### Get Profanity Config

```http
GET /api/v1/guilds/{guild_id}/profanity/config/
```

**Response:**
```json
{
  "enabled": true,
  "warn_threshold": 3,
  "mute_threshold": 5,
  "kick_threshold": 8,
  "ban_threshold": 10,
  "mute_duration": 3600,
  "delete_message": true,
  "dm_user": true
}
```

#### Update Profanity Config

```http
PATCH /api/v1/guilds/{guild_id}/profanity/config/
```

#### List Banned Words

```http
GET /api/v1/guilds/{guild_id}/profanity/words/
```

**Response:**
```json
{
  "count": 50,
  "results": [
    {
      "id": 1,
      "word": "badword",
      "language": "en",
      "severity": 3,
      "is_global": false
    }
  ]
}
```

#### Add Banned Word

```http
POST /api/v1/guilds/{guild_id}/profanity/words/
```

**Request:**
```json
{
  "word": "newbadword",
  "language": "en",
  "severity": 2
}
```

#### Delete Banned Word

```http
DELETE /api/v1/guilds/{guild_id}/profanity/words/{word_id}/
```

#### List Infractions

```http
GET /api/v1/guilds/{guild_id}/profanity/infractions/
```

**Query Parameters:**
- `user_id`: Filter by user
- `action_taken`: Filter by action (warn, mute, kick, ban)
- `date_from`: Start date
- `date_to`: End date

### Leveling

#### Get Leaderboard

```http
GET /api/v1/guilds/{guild_id}/leaderboard/
```

**Query Parameters:**
- `limit`: Number of results (default 10, max 100)

**Response:**
```json
{
  "results": [
    {
      "rank": 1,
      "user_id": "987654321",
      "username": "TopPlayer",
      "level": 50,
      "total_xp": 125000
    }
  ]
}
```

#### List Level Roles

```http
GET /api/v1/guilds/{guild_id}/level-roles/
```

#### Create Level Role

```http
POST /api/v1/guilds/{guild_id}/level-roles/
```

**Request:**
```json
{
  "level": 10,
  "role_id": "111222333444"
}
```

### Statistics

#### Get Guild Stats

```http
GET /api/v1/guilds/{guild_id}/stats/
```

**Response:**
```json
{
  "users": {
    "total": 150,
    "active_today": 45,
    "new_this_week": 12
  },
  "messages": {
    "total": 50000,
    "today": 500
  },
  "moderation": {
    "warnings": 25,
    "infractions": 15,
    "bans": 2
  },
  "leveling": {
    "total_xp": 500000,
    "average_level": 8.5,
    "max_level": 50
  }
}
```

## Error Responses

### 400 Bad Request

```json
{
  "error": "validation_error",
  "message": "Invalid input",
  "details": {
    "field": ["Error message"]
  }
}
```

### 401 Unauthorized

```json
{
  "error": "unauthorized",
  "message": "Authentication required"
}
```

### 403 Forbidden

```json
{
  "error": "forbidden",
  "message": "You don't have permission to access this resource"
}
```

### 404 Not Found

```json
{
  "error": "not_found",
  "message": "Resource not found"
}
```

### 429 Too Many Requests

```json
{
  "error": "rate_limited",
  "message": "Too many requests",
  "retry_after": 60
}
```

## Rate Limiting

- Default: 60 requests per minute
- Leaderboard: 10 requests per minute
- Bulk operations: 10 requests per minute

Headers included in response:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 55
X-RateLimit-Reset: 1234567890
```

## Webhooks (Coming Soon)

Configure webhooks to receive real-time events:

- `user.level_up`
- `moderation.warning`
- `moderation.infraction`
- `member.join`
- `member.leave`

## SDK Examples

### Python

```python
import requests

API_URL = "http://localhost:8000/api/v1"
API_KEY = "your-api-key"

headers = {"Authorization": f"Api-Key {API_KEY}"}

# Get guild users
response = requests.get(
    f"{API_URL}/guilds/123456789/users/",
    headers=headers
)
users = response.json()

# Add banned word
response = requests.post(
    f"{API_URL}/guilds/123456789/profanity/words/",
    headers=headers,
    json={"word": "badword", "severity": 2}
)
```

### JavaScript

```javascript
const API_URL = 'http://localhost:8000/api/v1';
const API_KEY = 'your-api-key';

// Get leaderboard
const response = await fetch(`${API_URL}/guilds/123456789/leaderboard/`, {
  headers: {
    'Authorization': `Api-Key ${API_KEY}`
  }
});
const leaderboard = await response.json();
```

### cURL

```bash
# Get guild config
curl -X GET "http://localhost:8000/api/v1/guilds/123456789/" \
  -H "Authorization: Api-Key YOUR_API_KEY"

# Update prefix
curl -X PATCH "http://localhost:8000/api/v1/guilds/123456789/" \
  -H "Authorization: Api-Key YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prefix": "?"}'
```
